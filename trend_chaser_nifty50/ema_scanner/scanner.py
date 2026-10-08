"""One serialized signal worker, independent stock recovery and immutable UI snapshots."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import math
import queue
import threading

from .broker import Broker, FeedQuote, normalize_token, parse_feed
from .history import MinuteBook, parse_time, regular_session, validate_history
from .indicators import EMAHistory
from .models import IST, Instrument, Settings, Snapshot, bucket_time
from .strategy import SignalMachine, rank_armed
from .trends import TrendBook


@dataclass
class StockState:
    instrument: Instrument
    machine: SignalMachine
    history: EMAHistory | None = None
    minutes: MinuteBook | None = None
    last_quote: FeedQuote | None = None
    row: Snapshot | None = None
    ready: bool = False
    reason: str = 'Loading history'
    pending: bool = False
    request_id: int = 0
    retry_at: datetime | None = None
    trend_validated: bool = False
    trend_quote_time: datetime | None = None


class Scanner:
    def __init__(self,settings: Settings,broker_factory=Broker,clock=lambda:datetime.now(IST),
                 start_worker=True,queue_size=4096,logger=None,trend_store=None):
        self.settings,self.broker_factory,self.clock,self.logger=settings,broker_factory,clock,logger
        self.trend_store=trend_store
        day=self.clock().astimezone(IST).date()
        # Startup file reads occur before the worker exists, never on the quote path.
        self.trends=TrendBook(day,trend_store.load(day) if trend_store else ())
        self._saved_trends=(day,self.trends.confirmed())
        self.lock=threading.RLock()
        self.queue=queue.Queue(maxsize=queue_size)
        self.stop=threading.Event()
        self.generation=0;self.epoch=0;self.overflow=False;self.event_sequence=0
        self.connected=False;self.connecting=False
        self.market_status='UNKNOWN';self.connection_status='Disconnected'
        self.states={};self.events=deque(maxlen=2000);self.diagnostics=deque(maxlen=300)
        self.broker=None;self.executor=None
        self.thread=None
        if start_worker:
            self.thread=threading.Thread(target=self._run,name='signal-worker',daemon=True)
            self.thread.start()

    def _enqueue(self,kind,payload,generation):
        if generation != self.generation or self.stop.is_set(): return
        try: self.queue.put_nowait((kind,payload,generation))
        except queue.Full:
            with self.lock: self.overflow=True

    def connect(self,token):
        token=normalize_token(token)
        self.disconnect()
        with self.lock:
            self.generation+=1
            gen=self.generation
            self.states={};self.events.clear()
            self.broker=self.broker_factory(token)
            broker=self.broker
            self.executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='history')
            self.connecting=True;self.connection_status='Loading current option-eligible stocks'
        def start():
            try:
                universe=broker.universe()
                self._enqueue('universe',universe,gen)
                if gen==self.generation:
                    broker.stream([i.key for i in universe[0]],lambda m:self._enqueue('feed',m,gen),
                                  lambda s:self._enqueue('status',s,gen))
            except Exception as exc:
                # Broker's generated errors are safe; unknown exceptions are reduced to type.
                message=str(exc) if type(exc) is RuntimeError and str(exc).startswith(('Upstox HTTP','Unable to download','No current','Connection cancelled','Unexpected Upstox','Upstox request')) else 'Connection failed; check token, network and Diagnostics.'
                self._enqueue('failure',message,gen)
        threading.Thread(target=start,name='broker-start',daemon=True).start()

    def disconnect(self):
        with self.lock:
            self.generation+=1;self.connected=False;self.connecting=False
            self.connection_status='Disconnected';self.market_status='UNKNOWN'
            broker,executor=self.broker,self.executor
            self.broker=None;self.executor=None
            for state in self.states.values(): self._pause(state,'Disconnected')
        if broker: broker.disconnect()
        if executor: executor.shutdown(wait=False,cancel_futures=True)

    def _emit(self,events):
        for event in events:
            self.event_sequence+=1
            event=replace(event,sequence=self.event_sequence)
            self.events.append(event)
            if self.logger: self.logger.write(event)

    def _market_events(self,events,snapshot):
        candidate=self.trends.candidates.get(snapshot.key)
        return [replace(event,price=snapshot.price,ema9=snapshot.ema9,ema21=snapshot.ema21,
                        candle_time=snapshot.bucket,
                        crossover_angle=(snapshot.angle if event.state=='CROSSED' else
                                         candidate.crossover_angle if candidate and candidate.side==event.side else None))
                for event in events]

    def _expire_provisionals(self):
        now=self.clock()
        for key,candidate in list(self.trends.candidates.items()):
            state=self.states.get(key)
            if (candidate.status=='PROVISIONAL' and state and state.trend_quote_time and
                    (now-state.trend_quote_time).total_seconds()>15):
                self._pause(state,'Quote older than 15 seconds')

    def _persist_trends(self):
        value=(self.trends.day,self.trends.confirmed())
        if value != self._saved_trends:
            self._saved_trends=value
            if self.trend_store: self.trend_store.save(value[1],value[0])

    def _roll_day(self):
        now=self.clock()
        day=now.astimezone(IST).date()
        if day != self.trends.day:
            self._emit(self.trends.reset_day(day,now))
            # Old histories may be incomplete at yesterday's close. Require the
            # ordinary broker validation before accepting today's opening quotes.
            self.epoch+=1
            for state in self.states.values():
                state.history=None;state.minutes=MinuteBook();state.last_quote=None
                state.row=None;state.pending=False;state.retry_at=None
                state.trend_validated=False;state.trend_quote_time=None
                self._pause(state,'New IST trading day; reconciling history')
            self._persist_trends()

    def _pause(self,state,reason,discard_provisional=True):
        state.ready=False;state.reason=reason
        self._emit(state.machine.pause(reason,self.clock()))
        self._emit(self.trends.pause(state.instrument.key,reason,self.clock(),discard_provisional))
        self._persist_trends()
        if state.row: state.row=state.machine.decorate(state.row)

    def _recover(self,state):
        if (not self.broker or not self.executor or not self.connected or state.pending or
                not regular_session(self.clock()) or self.market_status!='NORMAL_OPEN'): return
        now=self.clock()
        if state.retry_at and now<state.retry_at: return
        state.pending=True;state.request_id+=1
        gen,epoch,request=self.generation,self.epoch,state.request_id
        broker=self.broker
        def load():
            try: result,error=broker.history(state.instrument.key,self.clock()),None
            except Exception as exc: result,error=None,exc
            self._enqueue('history',(state.instrument.key,epoch,request,result,error),gen)
        try: self.executor.submit(load)
        except RuntimeError: state.pending=False

    def _process(self,kind,payload,generation):
        with self.lock:
            if generation!=self.generation: return
            self._roll_day()
            self._expire_provisionals()
            if kind=='universe':
                instruments,reasons=payload
                self.states={i.key:StockState(i,SignalMachine(i.symbol,self.settings),minutes=MinuteBook()) for i in instruments}
                self.diagnostics.extend(reasons)
                self.connection_status=f'Subscribing to {len(instruments)} underlying shares'
            elif kind=='status':
                if payload=='invalid':
                    for state in self.states.values():
                        state.history=None
                        self._pause(state,'Invalid feed payload; reconciling')
                    return
                self.connected=payload=='open';self.connecting=False
                self.connection_status='Connected — warming / checking quotes' if self.connected else 'Feed '+str(payload)+'; waiting for recovery'
                self.market_status='UNKNOWN'
                self.epoch+=1
                for state in self.states.values():
                    state.history=None;state.minutes=MinuteBook();state.last_quote=None;state.pending=False;state.retry_at=None
                    self._pause(state,'History reconciliation after '+str(payload))
            elif kind=='failure':
                self.connected=False;self.connecting=False;self.connection_status=payload
                self.diagnostics.append(payload)
                for state in self.states.values(): self._pause(state,'Connection failed')
            elif kind=='history':
                key,epoch,request,bars,error=payload
                state=self.states.get(key)
                if not state or epoch!=self.epoch or request!=state.request_id: return
                state.pending=False
                try:
                    if error: raise ValueError('history request failed')
                    validate_history(bars,self.clock())
                    state.history=EMAHistory(bars,state.instrument)
                    state.last_quote=None;state.retry_at=None
                    events,state.trend_validated=self.trends.verified_history(key,state.history,self.clock())
                    self._emit(events);self._persist_trends()
                    self._pause(state,'Waiting for a fresh quote after history validation',discard_provisional=False)
                except (ValueError,TypeError):
                    state.history=None;state.retry_at=self.clock()+timedelta(seconds=30)
                    self._pause(state,'Unable to validate history; retrying in 30 seconds')
            elif kind=='feed': self._feed(payload)

    def _feed(self,message):
        self._expire_provisionals()
        try:
            quotes,minutes,status=parse_feed(message)
            stamp=parse_time(message['currentTs'])
            if not -2 <= (self.clock()-stamp).total_seconds() <= 15: return
        except (KeyError,ValueError,TypeError,OverflowError,OSError):
            for state in self.states.values(): self._pause(state,'Invalid feed message; reconciling')
            return
        if status:
            self.market_status=status
            if status!='NORMAL_OPEN':
                for state in self.states.values(): self._pause(state,'Market '+status)
        now=self.clock()
        for key,rows in minutes.items():
            state=self.states.get(key)
            if not state: continue
            completed=[c for c in rows if c.time+timedelta(minutes=1)<=now]
            try:
                bars,gap=state.minutes.update(completed,bucket_time(now))
                for bar in bars:
                    if not state.history: break
                    if bar.time <= state.history.candles[-1].time:
                        original=next((c for c in reversed(state.history.candles) if c.time==bar.time),None)
                        if original and original!=bar:
                            self._pause(state,'Broker candle correction; reconciling')
                            state.history=None
                            break
                    elif bar.time==state.history.candles[-1].time+timedelta(minutes=5):
                        closed=state.history.snapshot(bar.close,bar.time,self.settings)
                        self._emit(self._market_events(state.machine.closed(closed),closed))
                        self._emit(self.trends.verified_candle(key,bar,closed.ema9,closed.ema21))
                        self._persist_trends()
                        state.history.append(bar)
                # Missing minutes matter only when history also lacks the completed bar.
                if gap and state.history and not self._covers(state.history,now):
                    self._pause(state,'Missing minute candles; backfill required',discard_provisional=False)
            except ValueError:
                self._pause(state,'Invalid minute candles; reconciling');state.history=None
        for q in quotes: self._quote(q,initial=q.initial)

    @staticmethod
    def _covers(history,now):
        start=now.astimezone(IST).replace(hour=9,minute=15,second=0,microsecond=0)
        expected=bucket_time(now)-timedelta(minutes=5)
        return history.candles[-1].time==expected if expected>=start else history.candles[-1].time<start

    def _quote(self,q: FeedQuote,initial=False):
        self._roll_day()
        self._expire_provisionals()
        state=self.states.get(q.key)
        if not state: return
        now=self.clock()
        if (not math.isfinite(q.price) or q.price<=0 or not -2<=(now-q.time).total_seconds()<=15 or
                not -2<=(now-q.message_time).total_seconds()<=15 or (q.time-q.message_time).total_seconds()>2):
            self._pause(state,'Invalid or stale quote timestamp');return
        if state.last_quote and q.time<state.last_quote.time:
            self._pause(state,'Out-of-order quote; waiting for fresh data');return
        if state.last_quote and (q.time-state.last_quote.time).total_seconds()>15:
            self._pause(state,'Quote observation gap longer than 15 seconds')
        state.last_quote=q;state.trend_quote_time=q.time
        if not self.connected or self.market_status!='NORMAL_OPEN' or not regular_session(now):
            self._pause(state,'Market closed or connection unavailable');return
        if bucket_time(q.time)!=bucket_time(now):
            self._pause(state,'Waiting for current five-minute quote');return
        if not state.history:
            self._pause(state,'Loading / reconciling history');self._recover(state);return
        if not self._covers(state.history,now):
            self._pause(state,'Missing completed candle; backfill required',discard_provisional=False);self._recover(state);return
        try: snapshot=state.history.snapshot(q.price,q.time,self.settings)
        except ValueError:
            self._pause(state,'Invalid indicator history');return
        self._emit(self.trends.observe(snapshot,initial=initial))
        self._emit(self._market_events(state.machine.observe(snapshot,initial=initial),snapshot))
        self._persist_trends()
        state.ready=True;state.reason='Ready';state.row=state.machine.decorate(snapshot)

    def _maintenance(self):
        with self.lock:
            import_day=getattr(self.broker,'constituent_import_day',None)
            if isinstance(import_day,date) and import_day!=self.clock().astimezone(IST).date():
                self.disconnect()
                self.connection_status='Nifty 50 CSV expired. Download and Load official CSV in Settings & Upstox, then connect again.'
                self.diagnostics.append(self.connection_status)
            self._roll_day()
            self._expire_provisionals()
            if self.overflow:
                self.overflow=False;self.epoch+=1
                while True:
                    try: self.queue.get_nowait()
                    except queue.Empty: break
                self.diagnostics.append('Input queue overflow: all observations paused and histories rescheduled.')
                for state in self.states.values():
                    state.history=None;state.pending=False;state.retry_at=None;state.minutes=MinuteBook();state.last_quote=None
                    self._pause(state,'Feed queue overflow; reconciling history')
            now=self.clock()
            for state in self.states.values():
                if state.ready and (not self.connected or self.market_status!='NORMAL_OPEN' or not regular_session(now)):
                    self._pause(state,'Market closed or connection unavailable')
                elif state.ready and state.last_quote and (now-state.last_quote.time).total_seconds()>15:
                    self._pause(state,'Quote older than 15 seconds')
                elif state.ready and (not state.history or not self._covers(state.history,now) or
                                      not state.row or state.row.bucket!=bucket_time(now)):
                    self._pause(state,'Missing completed candle or current quote; backfill required',discard_provisional=False)
                if self.connected and regular_session(now) and self.market_status=='NORMAL_OPEN' and (not state.history or not self._covers(state.history,now)):
                    self._recover(state)

    def _run(self):
        while not self.stop.is_set():
            try:
                kind,payload,gen=self.queue.get(timeout=.1)
                self._process(kind,payload,gen)
            except queue.Empty: pass
            except Exception:
                with self.lock:
                    self.diagnostics.append('Processing error: paused observations and scheduled reconciliation.')
                    self.overflow=True
            self._maintenance()

    def set_settings(self,settings: Settings):
        with self.lock:
            self.settings=settings
            for state in self.states.values():
                state.machine.settings=settings
                if state.ready and state.last_quote: self._quote(state.last_quote)

    def snapshot(self) -> dict:
        with self.lock:
            self._roll_day()
            now=self.clock()
            def actionable(s):
                return bool(s.row and s.ready and s.last_quote and s.history and
                            s.row.bucket==bucket_time(now) and self._covers(s.history,now) and
                            -2<=(now-s.last_quote.time).total_seconds()<=15 and self.connected and
                            self.market_status=='NORMAL_OPEN' and regular_session(now))
            rows=[s.row for s in self.states.values() if actionable(s)]
            trend_snapshots={key:s.row for key,s in self.states.items() if actionable(s) and s.trend_validated and
                             (key not in self.trends.candidates or
                              self.trends.candidates[key].checked_through == s.history.candles[-1].time)}
            candidates=list(self.trends.candidates.values())
            active=[c for c in candidates if c.key in trend_snapshots]
            trend_counts={'total':len(candidates),'long':sum(c.side=='LONG' for c in candidates),
                          'short':sum(c.side=='SHORT' for c in candidates),
                          'confirmed':sum(c.status=='CONFIRMED' for c in candidates),
                          'provisional':sum(c.status=='PROVISIONAL' for c in candidates),
                          'active_long':sum(c.side=='LONG' for c in active),
                          'active_short':sum(c.side=='SHORT' for c in active),
                          'hidden':len(candidates)-len(active)}
            receiving=sum(bool(s.last_quote and -2<=(now-s.last_quote.time).total_seconds()<=15) for s in self.states.values())
            ready=len(rows)
            return {'connected':self.connected,'connecting':self.connecting,'session_active':self.broker is not None,'status':self.connection_status,
                    'market':self.market_status,'settings':self.settings,'rows':rows,'armed':rank_armed(rows),
                    'counts':{'eligible':len(self.states),'subscribed':len(self.states) if self.connected else 0,
                              'receiving':receiving,'ready':ready,'paused':len(self.states)-ready},
                    'stocks':[(s.instrument.symbol,actionable(s),s.reason if not s.ready or actionable(s) else
                               'Waiting for current quote / verified candle') for s in self.states.values()],
                    'trends_long':self.trends.top('LONG',trend_snapshots,limit=7),
                    'trends_short':self.trends.top('SHORT',trend_snapshots,limit=7),
                    'trend_counts':trend_counts,
                    'trend_status':self.trend_store.error if self.trend_store and self.trend_store.error else
                                   ('Confirmed trends saved asynchronously' if self.trend_store else 'Trend persistence disabled'),
                    'events':list(self.events),'diagnostics':list(self.diagnostics)}

    def close(self):
        self.disconnect();self.stop.set()
        if self.thread: self.thread.join(timeout=2)
        if self.logger: self.logger.close()
        if self.trend_store: self.trend_store.close()

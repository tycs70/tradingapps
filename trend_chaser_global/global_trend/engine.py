"""Serialized market-data processing and immutable three-group dashboard views."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass,field,replace
from datetime import datetime,timedelta,timezone
from collections import deque
from types import MappingProxyType
import math
import queue
import threading
import time
import hashlib,json

from .models import Instrument,Settings,Snapshot,bucket_time
from .indicators import EMAHistory
from .trends import TrendBook,TrendRow
from .ranking import rank_group
from .catalog import GROUPS,default_catalog
from .calendar import trading_day
from .storage import TrendStore

UTC=timezone.utc


@dataclass(frozen=True)
class DisplayRow:
    key:str
    name:str
    group:str
    ctrader_name:str
    verified:bool=False
    rank:int|None=None
    side:str=''
    status:str='WAITING'
    captured_angle:float|None=None
    current_angle:float|None=None
    price:float|None=None
    quote_time:datetime|None=None
    signal_time:datetime|None=None
    ema9:float|None=None
    ema21:float|None=None
    distance_pct:float|None=None
    reason:str='Waiting for cTrader connection'
    snapshot:Snapshot|None=field(default=None,repr=False)
    digits:int|None=None


@dataclass(frozen=True)
class DashboardState:
    groups:object
    connected:bool
    status:str
    counts:object
    events:tuple=()
    diagnostics:tuple=()
    source:str='cTrader · Spotware Demo'
    sample:bool=False


@dataclass
class _AssetState:
    entry:object
    asset:object=None
    history:object=None
    quote:object=None
    row:object=None
    validated_bucket:object=None
    pending:bool=False
    request_id:int=0
    needs_baseline:bool=True
    reason:str='Waiting for cTrader connection'
    retry_at:object=None
    resume_after:object=None
    history_dirty:bool=False


class HistoryError(ValueError):pass


class Engine:
    def __init__(self,settings=None,logger=None,store=None,clock=None,entries=None,queue_size=8192):
        self.settings=settings or Settings();self.clock=clock or (lambda:datetime.now(UTC))
        self.logger=logger;self.store=store;self._store_path=store.path if store else None
        self.entries=tuple(default_catalog() if entries is None else entries)
        self._states={e.key:_AssetState(e) for e in self.entries};self._by_id={}
        if queue_size<1:raise ValueError('The quote queue must have a positive capacity.')
        self._lock=threading.RLock();self._inbox=queue.Queue(maxsize=queue_size+256)
        self._data_slots=threading.BoundedSemaphore(queue_size)
        self._overflow=threading.Event();self._fatal_overflow=threading.Event();self._stop=threading.Event()
        self._generation=0;self._epoch=0;self._client=None;self._executor=None;self._account=None
        self._connected=False;self._status='Disconnected';self._saved=None
        self._catalog_token=self._catalog_fingerprint()
        self.events=deque(maxlen=500);self.diagnostics=deque(maxlen=100);self._sequence=0
        self.book=TrendBook(self._day(self.clock()),day_key=self._day)
        self._thread=threading.Thread(target=self._run,name='global-trend-engine',daemon=True)
        self._thread.start()

    def _day(self,when):return trading_day(when,self.settings.day_boundary,self.settings.day_zone)

    def _catalog_fingerprint(self):
        # Scope persisted membership to instrument identity, verification and scoring geometry.
        values=sorted((e.key,e.group,e.olymp_name,e.ctrader_name,e.verified) for e in self.entries)
        payload=(values,self.settings.chart_bars,self.settings.angle_intervals,self.settings.day_boundary,self.settings.day_zone)
        return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]

    def reconfigure(self,settings):
        self.disconnect()
        with self._lock:
            self.settings=settings;self._catalog_token=None
            self.book=TrendBook(self._day(self.clock()),day_key=self._day)
            self._persist()

    def _enqueue(self,kind,payload,generation,epoch=None):
        if self._stop.is_set() or generation!=self._generation:return
        if epoch is None and kind in ('quote','bar_update'):epoch=self._epoch
        item=(kind,payload,generation,epoch)
        market=kind in ('quote','bar_update')
        if market and self._overflow.is_set():return
        if market and not self._data_slots.acquire(blocking=False):
            self._overflow.set();return
        try:self._inbox.put_nowait(item)
        except queue.Full:
            if market:self._data_slots.release();self._overflow.set()
            else:self._fatal_overflow.set()

    def _drain(self):
        retained=[]
        while True:
            try:item=self._inbox.get_nowait()
            except queue.Empty:break
            if item[0] in ('quote','bar_update'):self._data_slots.release()
            else:retained.append(item)
        return retained

    def connect(self,client,assets=None):
        self.disconnect()
        with self._lock:
            account=client.account_id
            if not account:raise ValueError('An authorized demo account is required.')
            catalog_token=self._catalog_fingerprint()
            if account!=self._account or catalog_token!=self._catalog_token:
                self._account=account;self.events.clear();self._saved=None
                self._catalog_token=catalog_token
                if self._store_path is not None:
                    if self.store:self.store.close()
                    path=self._store_path.with_name(self._store_path.stem+'-'+str(account)+'-'+catalog_token+self._store_path.suffix)
                    self.store=TrendStore(path,day_key=self._day)
                candidates=self.store.load(self._day(self.clock())) if self.store else ()
                self.book=TrendBook(self._day(self.clock()),candidates,day_key=self._day)
            self._client=client;self._status='Loading cTrader symbols and subscriptions'
            self._states={e.key:_AssetState(e) for e in self.entries};self._by_id={}
            self._executor=ThreadPoolExecutor(max_workers=3,thread_name_prefix='ctrader-history')
            generation=self._generation;executor=self._executor
        def prepare():
            try:
                resolved,reasons=client.resolve(self.entries) if assets is None else (list(assets),{})
                self._enqueue('assets',(resolved,reasons),generation)
                client.subscribe_assets(resolved,lambda kind,payload:self._enqueue(kind,payload,generation))
                self._enqueue('connected',None,generation)
            except Exception:
                self._enqueue('connection_error',None,generation)
        executor.submit(prepare)

    def disconnect(self):
        with self._lock:
            self._generation+=1;self._epoch+=1;self._connected=False;self._status='Disconnected'
            self._drain();self._overflow.clear();self._fatal_overflow.clear()
            client=self._client;executor=self._executor;self._client=None;self._executor=None
            for s in self._states.values():
                self._emit(self.book.pause(s.entry.key,'Disconnected',self.clock()))
                s.quote=None;s.row=None;s.pending=False;s.needs_baseline=True
                s.history_dirty=False
                s.validated_bucket=None;s.reason='Disconnected'
            self._persist()
        if client:client.close()
        if executor:executor.shutdown(wait=False,cancel_futures=True)

    def close(self):
        if self._stop.is_set():return
        self.disconnect();self._stop.set();self._thread.join(2)
        if self.store:self.store.close()
        if self.logger:self.logger.close()

    def _emit(self,events):
        for event in events:
            self._sequence+=1;event=replace(event,sequence=self._sequence)
            self.events.append(event)
            if self.logger:self.logger.write(event)
        self._persist()

    def _persist(self):
        if self.store:
            value=(self.book.day,self.book.confirmed())
            if value!=self._saved:
                self.store.save(value[1],value[0]);self._saved=value

    def _pause(self,s,reason,discard=True):
        s.reason=reason;s.needs_baseline=True
        self._emit(self.book.pause(s.entry.key,reason,self.clock(),discard_provisional=discard))

    def _request_history(self,s):
        if not self._connected or not self._executor or not s.asset or s.pending:return
        now=self.clock()
        if s.retry_at and now<s.retry_at:return
        s.pending=True;s.request_id+=1
        generation,epoch,request_id=self._generation,self._epoch,s.request_id
        client=self._client;asset=s.asset
        def load():
            try:
                end=self.clock();bars=client.history(asset,end-timedelta(days=3),end)
                if len(bars)<100:bars=client.history(asset,end-timedelta(days=14),end)
                self._validate_history(asset,bars,self.clock())
                result,error=bars,''
            except HistoryError as exc:result,error=None,str(exc)
            except Exception:result,error=None,'History loading failed; check data access and retry'
            self._enqueue('history',(s.entry.key,request_id,result,error),generation,epoch)
        try:self._executor.submit(load)
        except RuntimeError:s.pending=False

    def _validate_history(self,asset,bars,now):
        if len(bars)<100:raise HistoryError('Fewer than 100 completed candles')
        if not asset.schedule:raise HistoryError('Broker trading schedule unavailable')
        actual=[]
        for b in bars:
            if (not b.valid() or b.time!=bucket_time(b.time) or b.time+timedelta(minutes=5)>now):
                raise HistoryError('Invalid or incomplete historical candle')
            actual.append(b.time)
        if any(b<=a for a,b in zip(actual,actual[1:])):
            raise HistoryError('Historical candles are duplicated or out of order')
        expected=asset.schedule.expected_buckets(bars[0].time,bucket_time(now))
        if tuple(actual)!=expected:raise HistoryError('Missing or out-of-session candles; backfill required')

    def _publish(self,s,initial=False):
        now=self.clock()
        if not s.history or not s.quote or s.validated_bucket!=bucket_time(now):return
        if not -2<=(now-s.quote.time).total_seconds()<=15:return
        if bucket_time(s.quote.time)!=bucket_time(now):return
        if not s.asset.schedule.is_open(now):return
        s.row=s.history.snapshot(s.quote.bid,s.quote.time,self.settings)
        s.reason='Watching for an observed qualifying crossover'
        if s.entry.verified:
            self._emit(self.book.observe(s.row,initial=initial or s.needs_baseline))
        s.needs_baseline=False

    def _process(self,item):
        kind,payload,generation,epoch=item
        with self._lock:
            if generation!=self._generation:return
            if epoch is not None and epoch!=self._epoch:return
            if kind=='assets':
                resolved,reasons=payload
                for asset in resolved:
                    s=self._states.get(asset.entry.key)
                    if s:
                        s.asset=asset;s.entry=asset.entry;s.reason='Loading completed candles'
                        self._by_id[asset.symbol_id]=s
                for key,s in self._states.items():
                    if not s.asset:s.reason=reasons.get(key,'Symbol not offered by this account')
            elif kind=='connected':
                self._connected=True;self._status='Connected · cTrader Spotware Demo'
                for s in self._states.values():self._request_history(s)
            elif kind=='history':
                key,request_id,bars,error=payload;s=self._states.get(key)
                if not s or request_id!=s.request_id:return
                s.pending=False
                if s.history_dirty:
                    s.history_dirty=False;s.validated_bucket=None;s.retry_at=None
                    self._request_history(s);return
                if error:
                    s.validated_bucket=None;s.reason=error;s.retry_at=self.clock()+timedelta(seconds=2)
                    return
                s.history=EMAHistory(bars,Instrument(s.entry.olymp_name,s.entry.key))
                events,valid=self.book.verified_history(key,s.history,self.clock(),calendar=s.asset.schedule)
                self._emit(events)
                if not valid:
                    s.validated_bucket=None;s.reason='Required trend revalidation candles unavailable'
                    s.retry_at=self.clock()+timedelta(seconds=2);return
                s.validated_bucket=bucket_time(self.clock());s.retry_at=None
                self._publish(s,initial=True)
            elif kind=='quote':
                q=payload;s=self._by_id.get(q.symbol_id)
                if not s or q.bid is None or not math.isfinite(q.bid) or q.bid<=0:return
                age=(self.clock()-q.time).total_seconds()
                if not -2<=age<=15:return
                if s.resume_after is not None and q.time<=s.resume_after:return
                if s.quote and q.time<s.quote.time:return
                if s.quote and (q.time-s.quote.time).total_seconds()>15:
                    self._pause(s,'Quote continuity was lost')
                s.quote=q
                if s.validated_bucket!=bucket_time(self.clock()):
                    s.reason='Waiting for verified completed candles';self._request_history(s)
                else:self._publish(s)
            elif kind=='bar_update':
                s=self._by_id.get(payload)
                if s:
                    s.validated_bucket=None;s.reason='Broker bar updated; revalidating history'
                    s.history_dirty=s.pending
                    self._request_history(s)
            elif kind in ('disconnected','connection_error'):
                self.disconnect()
                self._status=('cTrader connection interrupted; reconnect to revalidate' if kind=='disconnected'
                              else 'Unable to prepare cTrader data; check authorization and network')

    def _maintenance(self):
        now=self.clock();day=self._day(now)
        if day!=self.book.day:
            self._emit(self.book.reset_day(day,now));self._epoch+=1
            for s in self._states.values():
                s.history=None;s.row=None;s.quote=None;s.validated_bucket=None;s.pending=False
                s.needs_baseline=True;s.retry_at=None;s.history_dirty=False
        if self._fatal_overflow.is_set():
            self.disconnect();self._status='Input queue overloaded; reconnect to revalidate'
            self.diagnostics.append(self._status);return
        if self._overflow.is_set():
            self._epoch+=1
            retained=self._drain()
            for item in retained:self._inbox.put_nowait(item)
            self.diagnostics.append('Quote queue overflow: data paused and history revalidation requested')
            for s in self._states.values():
                self._pause(s,'Queue overflow');s.quote=None;s.row=None
                s.resume_after=now
                s.validated_bucket=None;s.pending=False;s.retry_at=None
                s.history_dirty=False
            self._overflow.clear()
        if not self._connected:return
        for s in self._states.values():
            if not s.asset:continue
            if not s.asset.schedule.is_open(now):
                self._pause(s,'Market closed');continue
            if s.quote and (now-s.quote.time).total_seconds()>15:self._pause(s,'Quote older than 15 seconds')
            if s.validated_bucket!=bucket_time(now):self._request_history(s)

    def _run(self):
        last=0
        while not self._stop.is_set():
            try:
                item=self._inbox.get(timeout=.02)
                if item[0] in ('quote','bar_update'):self._data_slots.release()
                self._process(item)
            except queue.Empty:pass
            if self._overflow.is_set() or self._fatal_overflow.is_set() or time.monotonic()-last>=.1:
                with self._lock:self._maintenance()
                last=time.monotonic()

    def snapshot(self):
        with self._lock:
            self._maintenance();now=self.clock();groups={g:[] for g in GROUPS}
            counts={'eligible':len(self._states),'mapped':len(self._by_id),'history_ready':0,
                    'verified':sum(s.entry.verified for s in self._states.values()),'ranked':0,'fresh':0,
                    'history_pending':sum(s.pending for s in self._states.values()),
                    'revalidation_queued':sum(s.history_dirty for s in self._states.values())}
            for s in self._states.values():
                candidate=self.book.candidates.get(s.entry.key);snap=s.row
                fresh=bool(s.quote and -2<=(now-s.quote.time).total_seconds()<=15)
                covered=bool(s.history and s.validated_bucket==bucket_time(now))
                counts['history_ready']+=covered;counts['fresh']+=fresh
                status='WATCHING';reason=s.reason;active=False
                if not s.entry.verified:status='UNVERIFIED';reason='Verify the matching Olymp Trade instrument'
                elif not self._connected:status='DISCONNECTED'
                elif not s.asset:status='UNAVAILABLE'
                elif not s.asset.schedule.is_open(now):status='CLOSED';reason='Outside the broker trading session'
                elif s.quote and not fresh:status='STALE';reason='Quote older than 15 seconds'
                elif not covered:status='RECOVERING' if s.history else 'WARMING'
                elif not s.quote:status='WAITING';reason='Waiting for a fresh bid quote'
                elif (not snap or snap.bucket!=bucket_time(now) or
                      bucket_time(s.quote.time)!=bucket_time(now)):
                    status='RECOVERING';reason='Waiting for a quote aligned with the current candle'
                elif candidate:
                    status=candidate.status;active=True
                view=DisplayRow(s.entry.key,s.entry.olymp_name,s.entry.group,s.entry.ctrader_name,
                    verified=s.entry.verified,side=candidate.side if candidate else '',status=status,
                    captured_angle=candidate.crossover_angle if candidate else None,
                    current_angle=snap.angle if snap and snap.bucket==bucket_time(now) else None,
                    price=s.quote.bid if s.quote else None,quote_time=s.quote.time if s.quote else None,
                    signal_time=candidate.crossover_time if candidate else None,
                    ema9=snap.ema9 if snap else None,ema21=snap.ema21 if snap else None,
                    distance_pct=100*(snap.price-snap.ema9)/snap.ema9 if snap else None,
                    reason=reason,snapshot=snap,digits=s.asset.digits if s.asset else None)
                groups[s.entry.group].append((active,view,candidate,snap))
            out={}
            for group,items in groups.items():
                active=[i for i in items if i[0]]
                by_key={i[1].key:i[1] for i in active}
                ordered=rank_group([TrendRow(i[2],i[3]) for i in active])
                ranked=[replace(by_key[row.key],rank=n+1) for n,row in enumerate(ordered)]
                out[group]=tuple(ranked+[i[1] for i in items if not i[0]])
                counts['ranked']+=len(active)
            counts['paused']=len(self._states)-counts['ranked']
            return DashboardState(MappingProxyType(out),self._connected,self._status,
                                  MappingProxyType(counts),tuple(self.events),tuple(self.diagnostics))

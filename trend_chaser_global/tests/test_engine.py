from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest
from global_trend.models import Candle,Settings
from global_trend.calendar import MarketCalendar
from global_trend.catalog import CatalogEntry,ResolvedAsset
from global_trend.ctrader import Quote
from global_trend.engine import Engine

UTC=timezone.utc
NOW=datetime(2026,10,15,13,34,57,tzinfo=UTC)
BUCKET=NOW.replace(minute=30,second=0)


class Clock:
    def __init__(self,value=NOW):self.value=value
    def __call__(self):return self.value
    def advance(self,seconds):self.value+=timedelta(seconds=seconds)


def seed_bars(bucket=BUCKET):
    return [Candle(bucket-timedelta(minutes=5*(100-i)),100,100.2,99.8,100,1) for i in range(100)]


def assets(verified=True):
    return [ResolvedAsset(CatalogEntry(key,group,key,key,verified),i+1,2,
                          MarketCalendar([(0,604800)],'UTC'))
            for i,(key,group) in enumerate([('IDX','Indices'),('FX','Forex'),('STOCK','Shares')])]


class Broker:
    def __init__(self,items,bars=None,account_id=123):
        self.items=items;self.bars=list(bars or seed_bars());self.account_id=account_id
        self.callback=None;self.closed=False;self.subscribed=threading.Event()
    def resolve(self,entries):return self.items,{}
    def subscribe_assets(self,items,callback):self.callback=callback;self.subscribed.set()
    def history(self,asset,start,end):return list(self.bars)
    def emit(self,item,bid,stamp,ask=None):
        self.callback('quote',Quote(item.symbol_id,bid,ask,stamp))
    def close(self):self.closed=True


class LaggedBroker(Broker):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.hold=False;self.started=threading.Event();self.release=threading.Event()
    def history(self,asset,start,end):
        bars=list(self.bars)
        if self.hold and asset.entry.key=='STOCK':
            self.started.set();self.release.wait(3)
        return bars
    def close(self):self.release.set();super().close()


def wait_for(predicate,seconds=4):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        time.sleep(.005)
    raise AssertionError('Engine condition did not become true.')


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.items=assets();self.broker=Broker(self.items)
        self.engine=Engine(clock=self.clock,entries=[a.entry for a in self.items])
        self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
    def tearDown(self):self.engine.close()
    def row(self,key='STOCK'):
        return next(r for rows in self.engine.snapshot().groups.values() for r in rows if r.key==key)
    def tick(self,item,price):
        self.broker.emit(item,price,self.clock())
        wait_for(lambda:self.row(item.entry.key).price==price)
    def cross(self,item=None):
        item=item or self.items[2]
        self.tick(item,99.9);self.clock.advance(1);self.tick(item,100.1)
        wait_for(lambda:self.row(item.entry.key).status=='PROVISIONAL')

    def test_initial_snapshot_does_not_invent_a_crossover(self):
        self.tick(self.items[2],100.1)
        self.assertEqual(self.row().status,'WATCHING');self.assertIsNone(self.row().rank)

    def test_connection_state_distinguishes_interruption_from_manual_disconnect(self):
        self.assertEqual(self.engine.connection_state,'connected')
        self.broker.callback('disconnected','remote_closed')
        wait_for(lambda:self.engine.connection_state=='interrupted')
        self.assertFalse(self.engine.snapshot().connected)
        self.assertTrue(self.engine.snapshot().diagnostics)
        self.engine.disconnect()
        self.assertEqual(self.engine.connection_state,'idle')

    def test_mapping_change_discards_old_instrument_membership(self):
        from dataclasses import replace
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1);self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED')
        changed=replace(self.items[2].entry,ctrader_name='DIFFERENT')
        self.engine.entries=tuple(changed if e.key==changed.key else e for e in self.engine.entries)
        self.items[2]=replace(self.items[2],entry=changed,symbol_id=99)
        self.broker=Broker(self.items,self.broker.bars)
        self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        self.tick(self.items[2],100.15)
        self.assertIsNone(self.row().rank)

    def test_price_precision_follows_broker_symbol(self):
        self.assertEqual(self.row().digits,2)

    def test_queued_history_cannot_claim_coverage_of_a_later_candle(self):
        self.cross();original=self.engine._enqueue;queued=threading.Event();release=threading.Event()
        def hold(kind,payload,generation,epoch=None):
            if kind=='history' and payload[0]=='STOCK':
                queued.set();release.wait(3)
            return original(kind,payload,generation,epoch)
        self.engine._enqueue=hold
        try:
            self.broker.callback('bar_update',self.items[2].symbol_id)
            self.assertTrue(queued.wait(2))
            self.clock.value=BUCKET+timedelta(minutes=5,seconds=1)
            release.set();self.tick(self.items[2],100.12)
            wait_for(lambda:not self.engine.snapshot().counts['history_pending'])
            self.assertIsNone(self.row().rank)
            self.assertNotEqual(self.row().status,'PROVISIONAL')
        finally:release.set();self.engine._enqueue=original

    def test_partial_open_session_bar_is_valid_but_cannot_be_missing(self):
        from dataclasses import replace
        start=BUCKET-timedelta(minutes=5)
        second=((start.weekday()+1)%7)*86400+start.hour*3600+start.minute*60
        # Prior full session, then a one-minute reopen inside the final completed bar.
        cal=MarketCalendar([(0,second),(second+60,second+120),(second+300,604800)],'UTC')
        item=replace(self.items[2],schedule=cal)
        bars=seed_bars()
        self.engine._validate_history(item,bars,self.clock())
        with self.assertRaises(ValueError):self.engine._validate_history(item,bars[:-1],self.clock())

    def test_broker_retry_after_defers_history_retries(self):
        from global_trend.transport import RateLimitError
        original=self.broker.history;calls=[]
        def blocked(asset,start,end):
            if asset.entry.key=='STOCK':calls.append(self.clock());raise RateLimitError(120,2137)
            return original(asset,start,end)
        self.broker.history=blocked
        self.broker.callback('bar_update',self.items[2].symbol_id)
        wait_for(lambda:len(calls)==1 and not self.engine.snapshot().counts['history_pending'])
        self.clock.advance(3);self.engine.snapshot();time.sleep(.03)
        self.assertEqual(len(calls),1)
        self.clock.advance(118)
        wait_for(lambda:len(calls)==2)

    def test_history_authorization_rejection_stops_connection_and_retries(self):
        from global_trend.transport import AuthorizationError
        calls=[]
        def rejected(asset,start,end):
            calls.append(asset.entry.key);raise AuthorizationError()
        self.broker.history=rejected
        self.broker.callback('bar_update',self.items[2].symbol_id)
        wait_for(lambda:bool(calls) and not self.engine.snapshot().counts['history_pending'])
        self.assertEqual(self.engine.connection_state,'authorization_required')
        before=len(calls);self.clock.advance(10);self.engine.snapshot();time.sleep(.05)
        self.assertEqual(len(calls),before);self.assertTrue(self.broker.closed)

    def test_three_groups_rank_independently_and_keep_frozen_score(self):
        for item in self.items:
            self.tick(item,99.9);self.tick(item,100.1)
        wait_for(lambda:self.engine.snapshot().counts['ranked']==3)
        before=self.row().captured_angle
        self.tick(self.items[2],100.15)
        self.assertEqual(self.row().captured_angle,before)
        for group,rows in self.engine.snapshot().groups.items():self.assertEqual(rows[0].rank,1)

    def test_ask_only_update_does_not_refresh_bid_or_rank(self):
        self.cross();quote_time=self.row().quote_time;self.clock.advance(16)
        self.broker.emit(self.items[2],None,self.clock(),ask=101)
        wait_for(lambda:self.row().status=='STALE')
        self.assertEqual(self.row().quote_time,quote_time);self.assertIsNone(self.row().rank)

    def test_future_and_out_of_order_ticks_are_not_actionable(self):
        self.tick(self.items[2],99.9)
        self.broker.emit(self.items[2],101,self.clock()+timedelta(seconds=3))
        self.broker.emit(self.items[2],101,self.clock()-timedelta(seconds=1))
        time.sleep(.03)
        self.assertEqual(self.row().price,99.9);self.assertIsNone(self.row().rank)

    def test_small_clock_skew_cannot_rank_a_quote_from_the_next_bucket(self):
        self.cross()
        self.broker.emit(self.items[2],100.2,self.clock()+timedelta(seconds=2))
        wait_for(lambda:self.row().price==100.2)
        self.assertIsNone(self.row().rank)

    def test_closed_candle_confirms_and_later_adverse_close_removes(self):
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1)
        self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED')
        self.broker.bars.append(Candle(BUCKET+timedelta(minutes=5),100,100.2,98.8,99,1))
        self.clock.value=BUCKET+timedelta(minutes=10,seconds=1)
        self.tick(self.items[2],99)
        wait_for(lambda:any(e.state=='TREND_REMOVED' for e in self.engine.snapshot().events))
        self.assertIsNone(self.row().rank)

    def test_missing_completed_bar_hides_provisional_ranking(self):
        self.cross();self.clock.value=BUCKET+timedelta(minutes=5,seconds=1)
        self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='RECOVERING')
        self.assertIsNone(self.row().rank)

    def test_reconnect_checks_missed_adverse_bar_even_after_price_recovers(self):
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1);self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED');self.engine.disconnect()
        self.broker.bars.extend([Candle(BUCKET+timedelta(minutes=5*i),100,104,98,close,1)
                                 for i,close in [(1,99),(2,102),(3,103)]])
        self.clock.value=BUCKET+timedelta(minutes=20,seconds=1)
        self.broker=Broker(self.items,self.broker.bars)
        self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        self.tick(self.items[2],103)
        self.assertIsNone(self.row().rank)
        self.assertTrue(any('closed across EMA9' in e.reason for e in self.engine.snapshot().events))

    def test_old_connection_callbacks_cannot_feed_the_new_session(self):
        old_callback=self.broker.callback;self.engine.disconnect()
        self.broker=Broker(self.items);self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        old_callback('quote',Quote(3,999,None,self.clock()))
        self.tick(self.items[2],99.9)
        self.assertEqual(self.row().price,99.9);self.assertIsNone(self.row().rank)

    def test_unverified_match_has_prices_but_no_actionable_rank(self):
        self.engine.close();self.items=assets(False);self.broker=Broker(self.items)
        self.engine=Engine(clock=self.clock,entries=[a.entry for a in self.items])
        self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        self.tick(self.items[2],99.9);self.clock.advance(1);self.tick(self.items[2],100.1)
        self.assertEqual(self.row().status,'UNVERIFIED');self.assertIsNone(self.row().rank)

    def test_switching_account_does_not_reuse_other_accounts_trends(self):
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1);self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED')
        other=Broker(self.items,self.broker.bars,account_id=456)
        self.engine.connect(other,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        other.emit(self.items[2],100.2,self.clock())
        wait_for(lambda:self.row().price==100.2)
        self.assertIsNone(self.row().rank)

    def test_late_candle_correction_removes_confirmed_candidate(self):
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1);self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED')
        self.broker.bars[-1]=Candle(BUCKET,100,100.2,98.8,99,1)
        self.broker.callback('bar_update',self.items[2].symbol_id)
        wait_for(lambda:any(e.state=='TREND_REMOVED' for e in self.engine.snapshot().events))
        self.assertIsNone(self.row().rank)

    def test_overflow_recovery_does_not_replay_pre_break_quotes(self):
        self.engine.close()
        self.engine=Engine(clock=self.clock,entries=[a.entry for a in self.items],queue_size=2)
        self.broker=Broker(self.items);self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        old=self.clock()
        for _ in range(2000):self.broker.emit(self.items[2],99.9,old)
        wait_for(lambda:bool(self.engine.snapshot().diagnostics))
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        self.clock.advance(1)
        self.broker.emit(self.items[2],99.9,old)
        time.sleep(.03)
        self.tick(self.items[2],100.1)
        self.assertIsNone(self.row().rank)

    def test_first_opposing_quote_after_reconnect_removes_saved_side_only(self):
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1);self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED')
        self.engine.disconnect();self.broker=Broker(self.items,self.broker.bars)
        self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        self.tick(self.items[2],99)
        self.assertIsNone(self.row().rank)
        self.assertEqual(self.row().side,'')

    def test_revision_during_history_request_forces_a_second_reconciliation(self):
        self.cross();self.broker.bars.append(Candle(BUCKET,100,100.2,99.8,100.1,1))
        self.clock.value=BUCKET+timedelta(minutes=5,seconds=1);self.tick(self.items[2],100.12)
        wait_for(lambda:self.row().status=='CONFIRMED')
        self.broker=LaggedBroker(self.items,self.broker.bars)
        self.engine.connect(self.broker,self.items)
        wait_for(lambda:self.engine.snapshot().counts['history_ready']==3)
        self.tick(self.items[2],100.12);self.broker.hold=True
        self.broker.callback('bar_update',3)
        self.assertTrue(self.broker.started.wait(2))
        self.broker.bars[-1]=Candle(BUCKET,100,100.2,98.8,99,1)
        self.broker.callback('bar_update',3)
        wait_for(lambda:self.engine.snapshot().counts['revalidation_queued']==1)
        self.broker.release.set()
        wait_for(lambda:any(e.state=='TREND_REMOVED' for e in self.engine.snapshot().events))
        self.assertIsNone(self.row().rank)


if __name__=='__main__':unittest.main()

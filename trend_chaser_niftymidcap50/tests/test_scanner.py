import json
from pathlib import Path
import tempfile
import time
import unittest
from datetime import timedelta
from unittest.mock import Mock
from dataclasses import replace

from ema_scanner.models import Settings, Instrument
from ema_scanner.broker import FeedQuote
from ema_scanner.scanner import Scanner
from ema_scanner.storage import SettingsStore, InstanceLock
from ema_scanner.indicators import EMAHistory
from tests.test_data import NOW, session, minute


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self.clock=Mock(return_value=NOW)
        self.s=Scanner(Settings(),clock=self.clock,start_worker=False)
        self.s.generation=1
        self.s._process('universe',([Instrument('A','A'),Instrument('B','B')],[]),1)
        self.s._process('status','open',1)
        self.s.market_status='NORMAL_OPEN'
        self.bars=session(1)+session(2)+session(5,15)
        self.s._process('history',('A',self.s.epoch,0,self.bars,None),1)
        self.s._process('history',('B',self.s.epoch,0,self.bars,None),1)

    def tearDown(self): self.s.close()

    def quote(self,key='A',price=100,stamp=None,initial=False):
        return FeedQuote(key,price,stamp or NOW,self.clock(),initial)

    def test_ready_stock_independent_of_missing_other_history(self):
        self.s.states['B'].history=None
        self.s._quote(self.quote())
        data=self.s.snapshot()
        self.assertEqual(data['counts']['ready'],1)
        self.assertEqual(data['counts']['paused'],1)

    def test_stale_future_invalid_and_out_of_order_quotes_pause(self):
        self.s._quote(self.quote())
        for stamp in [NOW-timedelta(seconds=16),NOW+timedelta(seconds=3),NOW-timedelta(seconds=1)]:
            self.s._quote(self.quote(stamp=stamp))
            self.assertFalse(self.s.states['A'].ready)
        self.s._quote(self.quote(price=float('nan')))
        self.assertFalse(self.s.states['A'].ready)

    def test_stale_maintenance_and_closed_market_clear_ranking(self):
        self.s._quote(self.quote())
        self.clock.return_value=NOW+timedelta(seconds=16)
        self.s._maintenance()
        self.assertEqual(self.s.snapshot()['counts']['ready'],0)
        self.clock.return_value=NOW
        self.s.market_status='CLOSED'
        self.s._quote(self.quote())
        self.assertEqual(self.s.snapshot()['armed'],[])

    def test_old_generation_and_old_history_epoch_are_ignored(self):
        self.s._process('status','closed',0)
        self.assertTrue(self.s.connected)
        self.s._process('status','open',1)
        self.s._process('history',('A',self.s.epoch-1,0,self.bars,None),1)
        self.assertIsNone(self.s.states['A'].history)

    def test_rollover_missing_minutes_pauses_and_complete_bar_recovers(self):
        self.s._quote(self.quote())
        self.clock.return_value=NOW+timedelta(minutes=5)
        self.s._quote(self.quote(stamp=self.clock.return_value))
        self.assertFalse(self.s.states['A'].ready)
        self.assertIn('candle',self.s.states['A'].reason.lower())
        current=self.clock()
        ms=int(current.timestamp()*1000)
        rows=[]
        for i in range(5):
            c=minute(NOW+timedelta(minutes=i))
            rows.append({'interval':'I1','ts':int(c.time.timestamp()*1000),'open':c.open,'high':c.high,
                         'low':c.low,'close':c.close,'vol':c.volume})
        self.s._feed({'type':'live_feed','currentTs':ms,'feeds':{'A':{'ltpc':{'ltp':100,'ltt':ms},'marketOHLC':{'ohlc':rows}}}})
        self.assertTrue(self.s.states['A'].ready)
        self.assertEqual(self.s.states['A'].history.candles[-1].time,NOW)

    def test_overflow_pauses_and_resets_continuity(self):
        self.s._quote(self.quote())
        self.s.overflow=True
        self.s._maintenance()
        self.assertFalse(self.s.states['A'].ready)
        self.assertIsNone(self.s.states['A'].machine._relation)
        self.assertIn('overflow',self.s.states['A'].reason)

    def test_overflow_history_never_replays_a_pre_break_quote(self):
        self.s._quote(self.quote(price=90))
        self.s.overflow=True;self.s._maintenance()
        self.clock.return_value=NOW+timedelta(seconds=1)
        self.s._process('history',('A',self.s.epoch,0,self.bars,None),1)
        self.clock.return_value=NOW+timedelta(seconds=2)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        self.assertNotIn('CROSSED',[e.state for e in self.s.events])
        self.clock.return_value=NOW+timedelta(seconds=3)
        self.s._quote(self.quote(price=90,stamp=self.clock()))
        self.assertEqual(self.s.events[-1].state,'CROSSED')
        self.assertEqual(self.s.events[-1].side,'SHORT')

    def test_rollover_excludes_old_armed_row_even_before_maintenance(self):
        state=self.s.states['A']
        bars=[]
        for i,c in enumerate(self.bars):
            price=100-max(0,i-145)*.002
            bars.append(replace(c,open=price,high=price+.1,low=price-.1,close=price))
        state.history=EMAHistory(bars,state.instrument)
        h=state.history
        cross=(h.ema21[-1]*10/11-h.ema9[-1]*.8)/(.2-1/11)
        self.clock.return_value=NOW+timedelta(minutes=4,seconds=59)
        self.s._quote(self.quote(price=cross-.001,stamp=self.clock()))
        self.assertEqual(len(self.s.snapshot()['armed']),1)
        self.clock.return_value=NOW+timedelta(minutes=5,seconds=1)
        self.assertEqual(self.s.snapshot()['armed'],[])
        self.s._maintenance()
        self.assertFalse(state.ready)
        self.assertIn('candle',state.reason.lower())

    def test_history_failure_is_visible_without_sensitive_exception(self):
        self.s._process('history',('A',self.s.epoch,0,None,RuntimeError('secret_token')),1)
        self.assertIn('history',self.s.states['A'].reason)
        self.assertNotIn('secret_token',str(self.s.snapshot()))

    def test_reconnect_initial_observation_does_not_cross(self):
        self.s._quote(self.quote(price=90))
        self.s._process('status','open',1)
        self.s._process('history',('A',self.s.epoch,0,self.bars,None),1)
        self.s._quote(self.quote(price=110))
        self.assertNotIn('CROSSED',[e.state for e in self.s.events])


class StorageTest(unittest.TestCase):
    def test_trend_chase_remember_token_preference_defaults_on(self):
        self.assertTrue(Settings().remember_token)

    def test_settings_whitelist_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'settings.json'
            path.write_text(json.dumps({'proximity_pct':.07,'token':'SECRET'}))
            store=SettingsStore(path)
            settings=store.load()
            self.assertEqual(settings.proximity_pct,.07)
            store.save(settings)
            self.assertNotIn('SECRET',path.read_text())
            path.write_text('{corrupt')
            self.assertEqual(store.load(),Settings())

    def test_instance_lock_exclusive_and_reusable(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'instance.lock'
            a,b=InstanceLock(path),InstanceLock(path)
            self.assertTrue(a.acquire())
            self.assertFalse(b.acquire())
            a.release()
            self.assertTrue(b.acquire())
            b.release()



class TrendScannerTest(unittest.TestCase):
    setUp=ScannerTest.setUp
    tearDown=ScannerTest.tearDown
    quote=ScannerTest.quote

    def cross(self,side='LONG'):
        before,after=(90,110) if side=='LONG' else (110,90)
        self.clock.return_value=NOW+timedelta(minutes=4,seconds=58)
        self.s._quote(self.quote(price=before,stamp=self.clock()))
        self.clock.return_value=NOW+timedelta(minutes=4,seconds=59)
        self.s._quote(self.quote(price=after,stamp=self.clock()))
        return self.s.snapshot()['trends_long' if side=='LONG' else 'trends_short'][0]

    def backfill(self,closes):
        from ema_scanner.models import Candle
        bars=list(self.bars)
        for i,price in enumerate(closes):
            bars.append(Candle(NOW+timedelta(minutes=5*i),price,price+1,price-1,price))
        self.s._process('history',('A',self.s.epoch,self.s.states['A'].request_id,bars,None),1)
        return bars

    def test_observed_crosses_expose_immutable_rows_on_both_sides(self):
        for side in ['LONG','SHORT']:
            with self.subTest(side=side):
                self.s.trends.pause('A','test reset',self.clock())
                self.s.trends.candidates.clear()
                self.clock.return_value=NOW
                self.s.states['A'].last_quote=None
                row=self.cross(side)
                self.assertEqual(row.status,'PROVISIONAL')
                self.assertEqual(row.side,side)
                self.assertGreater(row.strength,0)
                self.assertEqual(row.key,row.snapshot.key)
                self.assertEqual(row.distance_pct,100*(row.price-row.ema9)/row.ema9)
                self.assertEqual(self.s.snapshot()['trend_counts']['provisional'],1)

    def test_routine_missing_minutes_backfill_confirms_before_fresh_quote_activation(self):
        row=self.cross();angle=row.crossover_angle
        self.clock.return_value=NOW+timedelta(minutes=5)
        self.s._maintenance()
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        self.assertEqual(self.s.trends.candidates['A'].status,'PROVISIONAL')
        self.backfill([110])
        self.assertEqual(self.s.trends.candidates['A'].status,'CONFIRMED')
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        self.s._quote(self.quote(price=111,stamp=self.clock()))
        rows=self.s.snapshot()['trends_long']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].crossover_angle,angle)
        self.assertNotEqual(rows[0].current_angle,angle)
        self.assertEqual(rows[0].candidate.checked_through,NOW)
        self.assertTrue(any(e.state=='TREND_CONFIRMED' for e in self.s.events))

    def test_actual_staleness_discards_provisional_and_suppresses_resumed_cross(self):
        self.cross()
        self.clock.return_value=NOW+timedelta(minutes=5,seconds=15)
        self.s._maintenance()
        self.assertNotIn('A',self.s.trends.candidates)
        self.s._quote(self.quote(price=90,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trends_short'],[])

    def test_minute_aggregation_confirms_crossing_candle(self):
        self.cross()
        self.clock.return_value=NOW+timedelta(minutes=5)
        ms=int(self.clock().timestamp()*1000)
        rows=[{'interval':'I1','ts':int((NOW+timedelta(minutes=i)).timestamp()*1000),
               'open':110,'high':120,'low':80,'close':110,'vol':1} for i in range(5)]
        self.s._feed({'type':'live_feed','currentTs':ms,'feeds':{'A':{'ltpc':{'ltp':110,'ltt':ms},
                       'marketOHLC':{'ohlc':rows}}}})
        self.assertEqual(self.s.snapshot()['trends_long'][0].status,'CONFIRMED')

    def test_missed_adverse_close_then_recovery_removes_permanently(self):
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5)
        self.backfill([110]);self.s._quote(self.quote(price=111,stamp=self.clock()))
        self.s._process('status','closed',1)
        self.assertIn('A',self.s.trends.candidates)
        self.clock.return_value=NOW+timedelta(minutes=15)
        self.s._process('status','open',1);self.s.market_status='NORMAL_OPEN'
        self.backfill([110,80,120])
        self.s._quote(self.quote(price=121,stamp=self.clock()))
        self.assertNotIn('A',self.s.trends.candidates)
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        removals=[e for e in self.s.events if e.state=='TREND_REMOVED']
        self.assertEqual(removals[-1].candle_time,NOW+timedelta(minutes=5))
        self.assertEqual(removals[-1].price,80)
        self.assertGreater(removals[-1].ema9,80)

    def test_unavailable_revalidation_hides_confirmed_until_all_required_bars_exist(self):
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5)
        bars=self.backfill([110]);self.s._quote(self.quote(price=111,stamp=self.clock()))
        self.clock.return_value=NOW+timedelta(minutes=15)
        from ema_scanner.models import Candle
        incomplete=bars+[Candle(NOW+timedelta(minutes=10),120,121,119,120)]
        self.s._process('history',('A',self.s.epoch,0,incomplete,None),1)
        self.s._quote(self.quote(price=121,stamp=self.clock()))
        self.assertIn('A',self.s.trends.candidates)
        self.assertEqual(self.s.snapshot()['trends_long'],[])

    def test_confirmed_stale_snapshot_hidden_before_worker_maintenance(self):
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5)
        self.backfill([110]);self.s._quote(self.quote(price=111,stamp=self.clock()))
        self.clock.return_value+=timedelta(seconds=16)
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        self.assertIn('A',self.s.trends.candidates)
        self.s._maintenance()
        self.assertEqual(self.s.snapshot()['trend_counts']['confirmed'],1)
        self.assertEqual(self.s.snapshot()['trend_counts']['hidden'],1)

    def test_fresh_quote_after_unobserved_silence_does_not_invent_cross(self):
        self.s._quote(self.quote(price=90))
        self.clock.return_value=NOW+timedelta(seconds=16)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        self.assertFalse(any(e.state=='TREND_ADDED' for e in self.s.events))

    def test_backfill_wait_does_not_keep_stale_provisional_forever(self):
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5)
        self.s._maintenance()
        self.assertIn('A',self.s.trends.candidates)
        self.clock.return_value+=timedelta(seconds=15)
        self.s._maintenance()
        self.assertNotIn('A',self.s.trends.candidates)
        self.backfill([110])
        self.s._quote(self.quote(price=111,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trends_long'],[])

    def test_delayed_history_cannot_confirm_a_stale_provisional(self):
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5,seconds=15)
        self.backfill([110])
        self.assertNotIn('A',self.s.trends.candidates)

    def test_normal_cross_events_include_public_market_geometry(self):
        self.cross()
        event=next(e for e in reversed(self.s.events) if e.state=='CROSSED')
        row=self.s.snapshot()['trends_long'][0]
        self.assertEqual(event.price,row.price)
        self.assertEqual(event.ema9,row.ema9)
        self.assertEqual(event.ema21,row.ema21)
        self.assertEqual(event.candle_time,NOW)
        self.assertEqual(event.crossover_angle,row.crossover_angle)

    def test_angle_settings_never_change_frozen_ranking(self):
        row=self.cross()
        self.s.set_settings(replace(self.s.settings,chart_bars=120,angle_intervals=5))
        new=self.s.snapshot()['trends_long'][0]
        self.assertEqual(new.candidate,row.candidate)
        self.assertNotEqual(new.current_angle,row.current_angle)

    def test_daily_rollover_resets_in_ongoing_process_even_without_maintenance(self):
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5)
        self.backfill([110]);self.s._quote(self.quote(price=111,stamp=self.clock()))
        self.clock.return_value+=timedelta(days=1)
        self.assertEqual(self.s.snapshot()['trend_counts']['total'],0)
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        self.assertEqual(self.s.trends.candidates,{})

    def test_new_day_complete_prior_history_reconciles_before_opening_trend(self):
        from concurrent.futures import ThreadPoolExecutor
        from ema_scanner.models import Candle
        import threading
        full=session(1)+session(2)+session(5)
        self.clock.return_value=NOW.replace(hour=15,minute=30)
        self.s._process('history',('A',self.s.epoch,0,full,None),1)
        self.s.states={'A':self.s.states['A']}
        requested=threading.Event()
        class HistoryBroker:
            def history(inner,key,now):
                requested.set();return full
            def disconnect(inner): pass
        self.s.broker=HistoryBroker()
        self.s.executor=ThreadPoolExecutor(max_workers=1)
        opening=(NOW+timedelta(days=1)).replace(hour=9,minute=16)
        self.clock.return_value=opening
        self.s._quote(self.quote(price=90,stamp=self.clock()))
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trend_counts']['total'],0)
        self.assertFalse(self.s.states['A'].ready)
        self.assertIsNone(self.s.states['A'].history)
        self.assertTrue(requested.wait(2),'New-day history recovery was not requested')
        kind,payload,generation=self.s.queue.get(timeout=2)
        self.assertEqual(kind,'history')
        self.s._process(kind,payload,generation)
        self.assertTrue(self.s.states['A'].trend_validated)
        self.assertEqual(self.s.snapshot()['trends_long'],[])
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trend_counts']['total'],0,
                         'History must not replay pre-validation quote crossings')
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=90,stamp=self.clock()))
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        row=self.s.snapshot()['trends_long'][0]
        self.assertEqual(row.status,'PROVISIONAL')
        self.assertEqual(row.crossover_time,self.clock())
        self.assertEqual(row.candidate.checked_through,full[-1].time)
    def test_new_day_incomplete_prior_history_cannot_supply_a_frozen_cross(self):
        old=self.s.states['A'].history
        opening=(NOW+timedelta(days=1)).replace(hour=9,minute=16)
        self.clock.return_value=opening
        self.s._quote(self.quote(price=90,stamp=self.clock()))
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trend_counts']['total'],0)
        self.assertFalse(self.s.states['A'].ready)
        self.assertIsNone(self.s.states['A'].history)
        self.s._process('history',('A',self.s.epoch,0,old.candles,None),1)
        self.assertIsNone(self.s.states['A'].history)
        self.assertEqual(self.s.snapshot()['trend_counts']['total'],0)
        full=session(1)+session(2)+session(5)
        self.s._process('history',('A',self.s.epoch,0,full,None),1)
        self.assertTrue(self.s.states['A'].trend_validated)
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=90,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trend_counts']['total'],0)
        self.clock.return_value+=timedelta(seconds=1)
        self.s._quote(self.quote(price=110,stamp=self.clock()))
        self.assertEqual(self.s.snapshot()['trends_long'][0].status,'PROVISIONAL')

    def test_restart_confirmed_requires_same_day_history_and_fresh_quote(self):
        from ema_scanner.storage import TrendStore
        self.cross();self.clock.return_value=NOW+timedelta(minutes=5)
        bars=self.backfill([110])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'trends.json';store=TrendStore(path)
            store.save(self.s.trends.confirmed(),NOW.date());store.flush()
            scanner=Scanner(Settings(),clock=self.clock,start_worker=False,trend_store=store)
            try:
                scanner.generation=1
                scanner._process('universe',([Instrument('A','A')],[]),1)
                scanner._process('status','open',1);scanner.market_status='NORMAL_OPEN'
                self.assertEqual(scanner.snapshot()['trends_long'],[])
                self.assertEqual(scanner.snapshot()['trend_counts']['confirmed'],1)
                scanner._process('history',('A',scanner.epoch,0,bars,None),1)
                self.assertEqual(scanner.snapshot()['trends_long'],[])
                scanner._quote(self.quote(price=111,stamp=self.clock()))
                self.assertEqual(scanner.snapshot()['trends_long'][0].status,'CONFIRMED')
                self.clock.return_value+=timedelta(days=1)
                scanner._maintenance();store.flush()
                self.assertEqual(store.load(self.clock().date()),[])
            finally: scanner.close()


if __name__=='__main__': unittest.main()

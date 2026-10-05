import json
from pathlib import Path
import tempfile
import time
import unittest
from datetime import timedelta
from unittest.mock import Mock

from ema_scanner.models import Settings, Instrument
from ema_scanner.broker import FeedQuote
from ema_scanner.scanner import Scanner
from ema_scanner.storage import SettingsStore, InstanceLock
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


if __name__=='__main__': unittest.main()

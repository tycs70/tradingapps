"""Trend membership is earned by observations, never reconstructed from history."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ema_scanner.models import Candle, IST, Instrument, Settings
from ema_scanner.indicators import EMAHistory
from ema_scanner.trends import TrendBook, TrendCandidate, TrendRow
from ema_scanner.storage import TrendStore, EventLogger
from tests.test_data import NOW, session


def snap(side='LONG', crossed=True, key='A', angle=20, at=NOW):
    history = EMAHistory(session(1)+session(2)+session(5,15), Instrument(key,key))
    row = history.snapshot(100, at, Settings())
    direction = 1 if side == 'LONG' else -1
    relation = direction if crossed else -direction
    return replace(row, ema9=100 + relation*.1, ema21=100,
                   price=100+direction, angle=direction*angle)


def observed(book, side='LONG', key='A', angle=20):
    book.observe(snap(side,False,key,angle))
    return book.observe(snap(side,True,key,angle,at=NOW+timedelta(seconds=1)))


def bar(at=NOW, close=101):
    return Candle(at,100,max(110,close),min(90,close),close)


class TrendBookTest(unittest.TestCase):
    def setUp(self): self.book=TrendBook(NOW.date())

    def test_observed_crossover_add_confirm_mirrors_and_records_details(self):
        for side, key, close, e9 in [('LONG','A',101,100.1),('SHORT','B',99,99.9)]:
            events=observed(self.book,side,key)
            self.assertEqual(events[-1].state,'TREND_ADDED')
            self.assertEqual(events[-1].price,close)
            self.assertEqual(events[-1].ema9,e9)
            self.assertEqual(events[-1].crossover_angle,20 if side=='LONG' else -20)
            self.assertEqual(events[-1].candle_time,NOW)
            c=self.book.candidates[key]
            self.assertEqual(c.status,'PROVISIONAL')
            self.assertEqual(c.crossover_time,NOW+timedelta(seconds=1))
            events=self.book.verified_candle(key,bar(close=close),e9,100)
            self.assertEqual(events[-1].state,'TREND_CONFIRMED')
            self.assertEqual(events[-1].time,NOW+timedelta(minutes=5))
            self.assertEqual(self.book.candidates[key].checked_through,NOW)
            self.assertEqual(self.book.candidates[key].status,'CONFIRMED')

    def test_no_initial_snapshot_or_history_creates_membership(self):
        self.assertEqual(self.book.observe(snap()),[])
        self.assertEqual(self.book.verified_candle('A',bar(),100.1,100),[])
        self.book.pause('A','disconnect',NOW)
        self.assertEqual(self.book.observe(snap('SHORT')),[])
        self.assertEqual(self.book.candidates,{})

    def test_direction_aligned_angle_and_price_are_required_without_minimum(self):
        for side in ['LONG','SHORT']:
            for angle,wrong_price,expected in [(0,False,False),(-1,False,False),(.00001,False,True),(20,True,False)]:
                with self.subTest(side=side,angle=angle,wrong_price=wrong_price):
                    b=TrendBook(NOW.date());b.observe(snap(side,False))
                    row=snap(side,angle=angle)
                    if wrong_price: row=replace(row,price=row.ema9)
                    b.observe(row)
                    self.assertEqual(bool(b.candidates),expected)

    def test_provisional_requires_crossing_bar_relationship_and_strict_price_side(self):
        for side in ['LONG','SHORT']:
            sign=1 if side=='LONG' else -1
            for close,e9 in [(100+sign,100-sign*.1),(100+sign*.1,100+sign*.1)]:
                with self.subTest(side=side,close=close,e9=e9):
                    b=TrendBook(NOW.date());observed(b,side)
                    self.assertEqual(b.verified_candle('A',bar(close=close),e9,100)[-1].state,'TREND_REMOVED')
                    self.assertFalse(b.candidates)

    def test_confirmed_wicks_intrabar_and_equality_preserve_adverse_close_removes(self):
        for side in ['LONG','SHORT']:
            sign=1 if side=='LONG' else -1
            b=TrendBook(NOW.date());observed(b,side)
            b.verified_candle('A',bar(close=100+sign),100+sign*.1,100)
            b.observe(replace(snap(side),price=100-sign*5))
            self.assertIn('A',b.candidates)
            b.verified_candle('A',bar(NOW+timedelta(minutes=5),100+sign*.1),100+sign*.1,100)
            self.assertIn('A',b.candidates)
            events=b.verified_candle('A',bar(NOW+timedelta(minutes=10),100-sign),100+sign*.1,100)
            self.assertEqual(events[-1].state,'TREND_REMOVED')
            self.assertIn('close',events[-1].reason.lower())
            b.verified_candle('A',bar(NOW+timedelta(minutes=15),100+sign),100+sign*.1,100)
            b.observe(snap(side))
            self.assertNotIn('A',b.candidates)

    def test_provisional_reversal_removes_and_new_side_independently_qualifies(self):
        observed(self.book)
        events=self.book.observe(snap('SHORT',angle=-1))
        self.assertEqual([e.state for e in events],['TREND_REMOVED'])
        self.assertNotIn('A',self.book.candidates)
        self.book.observe(snap('LONG'))
        self.book.observe(snap('SHORT'))
        self.assertEqual(self.book.candidates['A'].side,'SHORT')

    def test_pause_discards_provisional_retains_confirmed_and_resets_observation(self):
        observed(self.book,key='A');observed(self.book,key='B')
        self.book.verified_candle('B',bar(),100.1,100)
        self.book.pause('A','Disconnected',NOW);self.book.pause('B','Disconnected',NOW)
        self.assertNotIn('A',self.book.candidates)
        self.assertIn('B',self.book.candidates)
        self.assertEqual(self.book.observe(snap('SHORT',key='A')),[])

    def test_provisional_continuity_removal_retains_last_observed_market_details(self):
        observed(self.book)
        event=self.book.pause('A','Disconnected',NOW+timedelta(seconds=2))[-1]
        self.assertEqual(event.price,101)
        self.assertEqual(event.ema9,100.1)
        self.assertEqual(event.ema21,100)
        self.assertEqual(event.candle_time,NOW)
        self.assertEqual(event.crossover_angle,20)

    def test_routine_boundary_can_verify_provisional_from_backfill(self):
        observed(self.book)
        self.book.pause('A','Waiting for completed candle',NOW+timedelta(minutes=5),discard_provisional=False)
        self.book.verified_candle('A',bar(),100.1,100)
        self.assertEqual(self.book.candidates['A'].status,'CONFIRMED')

    def test_frozen_strength_top5_replacement_and_ties_are_stable(self):
        snapshots={}
        for side in ['LONG','SHORT']:
            for i in range(7):
                key=f'{side}{i}';observed(self.book,side,key,angle=i+1)
                snapshots[key]=replace(snap(side,key=key),angle=(100-i)*(1 if side=='LONG' else -1))
            rows=self.book.top(side,snapshots)
            self.assertEqual([r.key for r in rows],[f'{side}{i}' for i in range(6,1,-1)])
            self.assertEqual(rows[0].current_angle,94 if side=='LONG' else -94)
            self.assertEqual(rows[0].crossover_angle,7 if side=='LONG' else -7)
            with self.assertRaises(FrozenInstanceError): rows[0].candidate.crossover_angle=999
            with self.assertRaises(FrozenInstanceError): rows[0].snapshot=snap()
            self.book.pause(f'{side}6','Disconnected',NOW)
            self.assertEqual(self.book.top(side,snapshots)[-1].key,f'{side}1')
        b=TrendBook(NOW.date());observed(b,key='Z');observed(b,key='A')
        self.assertEqual([r.symbol for r in b.top('LONG',{'A':snap(key='A'),'Z':snap(key='Z')})],['A','Z'])

    def test_verified_bar_advances_relation_without_creating_membership(self):
        self.book.observe(snap('LONG',False))
        self.book.verified_candle('A',bar(),100.1,100)
        self.assertEqual(self.book.observe(snap('LONG')),[])
        self.assertEqual(self.book.candidates,{})
        events=self.book.observe(snap('SHORT'))
        self.assertEqual(events[-1].state,'TREND_ADDED')
        self.assertEqual(events[-1].side,'SHORT')

    def test_new_day_clears_candidates_and_observation_baseline(self):
        observed(self.book)
        self.assertTrue(self.book.reset_day(NOW.date()+timedelta(days=1),NOW+timedelta(days=1)))
        self.assertFalse(self.book.candidates)
        self.assertEqual(self.book.observe(replace(snap(),quote_time=NOW+timedelta(days=1))),[])


class TrendPersistenceTest(unittest.TestCase):
    def candidate(self,side='LONG',status='CONFIRMED'):
        return TrendCandidate('A','A',side,NOW,20 if side=='LONG' else -20,status,NOW)

    def test_confirmed_only_async_atomic_snapshot_and_same_day_load(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'trends.json';store=TrendStore(path)
            candidates=[self.candidate(),replace(self.candidate(status='PROVISIONAL'),key='B',symbol='B')]
            calling_thread=threading.get_ident();writers=[]
            original=Path.write_text
            def record_write(path,*args,**kwargs):
                writers.append(threading.get_ident());return original(path,*args,**kwargs)
            with patch.object(Path,'write_text',record_write):
                store.save(candidates,NOW.date());candidates.clear();store.flush()
            loaded=store.load(NOW.date())
            self.assertEqual(loaded,[self.candidate()])
            self.assertTrue(writers)
            self.assertNotIn(calling_thread,writers)
            self.assertEqual(list(path.parent.glob('*.tmp')),[])
            self.assertEqual(store.load(NOW.date()+timedelta(days=1)),[])
            store.close();store.close()

    def test_graceful_close_waits_for_ordered_removal_and_concurrent_close(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'trends.json';store=TrendStore(path)
            store.save([self.candidate()],NOW.date());store.flush()
            removal_started=threading.Event();release=threading.Event()
            first_done=threading.Event();second_done=threading.Event()
            writes=[];original=Path.write_text
            def controlled_write(target,content,*args,**kwargs):
                record=json.loads(content);writes.append(len(record['candidates']))
                if not record['candidates']:
                    removal_started.set();release.wait()
                return original(target,content,*args,**kwargs)
            def close_and_mark(done):
                store.close();done.set()
            first=threading.Thread(target=close_and_mark,args=(first_done,),daemon=True)
            second=threading.Thread(target=close_and_mark,args=(second_done,),daemon=True)
            with patch.object(Path,'write_text',controlled_write):
                try:
                    later=replace(self.candidate(),checked_through=NOW+timedelta(minutes=5))
                    store.save([later],NOW.date());store.save([],NOW.date())
                    self.assertTrue(removal_started.wait(2))
                    self.assertEqual(store.load(NOW.date()),[later])
                    first.start()
                    self.assertFalse(first_done.wait(2.2),
                                     'Graceful close returned while a removal was still pending')
                    second.start()
                    self.assertFalse(second_done.wait(.1),
                                     'Repeated close must wait for the same pending writer')
                    self.assertTrue(store.thread.is_alive())
                finally:
                    release.set()
                    if first.ident is not None: first.join(2)
                    if second.ident is not None: second.join(2)
                    store.close()
                    store.thread.join(2)
            self.assertTrue(first_done.is_set());self.assertTrue(second_done.is_set())
            self.assertFalse(store.thread.is_alive())
            self.assertEqual(store.queue.unfinished_tasks,0)
            self.assertEqual(store.load(NOW.date()),[])
            self.assertEqual(writes,[1,0])
            store.close()

    def test_corrupt_untrusted_and_nonfinite_records_rejected_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'trends.json';store=TrendStore(path)
            store.save([self.candidate()],NOW.date());store.flush()
            good=json.loads(path.read_text())
            invalid=['{broken',json.dumps({'token':'SECRET'}),'[]']
            for field,value in [('side','OTHER'),('status','PROVISIONAL'),('crossover_angle',float('nan')),
                                ('checked_through',None),('crossover_time','2026-10-05T10:30:00')]:
                obj=json.loads(json.dumps(good));obj['candidates'][0][field]=value;invalid.append(json.dumps(obj))
            for content in invalid:
                path.write_text(content)
                self.assertEqual(store.load(NOW.date()),[])
            store.close()

    def test_rich_events_are_json_serializable_and_keep_legacy_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            logger=EventLogger(Path(temp));b=TrendBook(NOW.date())
            for event in observed(b): logger.write(event)
            logger.close()
            records=[json.loads(line) for path in Path(temp).glob('*.jsonl') for line in path.read_text().splitlines()]
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['state'],'TREND_ADDED')
            self.assertEqual(records[0]['price'],101)
            self.assertEqual(records[0]['ema21'],100)
            self.assertEqual(records[0]['candle_time'],NOW.isoformat())
            self.assertIn('initial',records[0]);self.assertIn('sequence',records[0])

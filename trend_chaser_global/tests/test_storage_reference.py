from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from global_trend.storage import TrendStore, EventLogger
from global_trend.trends import TrendCandidate, TrendBook
from tests.test_data import NOW
from tests.test_trends import observed

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

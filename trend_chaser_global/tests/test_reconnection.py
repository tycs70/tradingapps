"""Real scanner/controller recovery, with only the broker I/O replaced."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile,time,unittest
from global_trend.auth import TokenBundle
from global_trend.connection import ConnectionController
from global_trend.credentials import CredentialStore
from global_trend.engine import Engine
from global_trend.models import Candle
from tests.test_engine import Broker,Clock,assets,seed_bars,BUCKET,wait_for


class RecoveryIntegrationTest(unittest.TestCase):
    def test_automatic_reconnect_revalidates_every_missed_close_before_ranking(self):
        clock=Clock();items=assets();bars=seed_bars();created=[];retry_clock=[0.0]
        class DemoBroker(Broker):
            def __init__(self,*args):
                super().__init__(items,bars);self.bars=bars;created.append(self)
            def accounts(self,tokens):
                return ({'account_id':123,'login':5923508,'is_live':False,'broker':'Spotware'},)
            def authorize(self,account,tokens):self.account_id=account
        def finished(controller):
            controller.poll();return not controller.busy
        engine=Engine(clock=clock,entries=[a.entry for a in items])
        with tempfile.TemporaryDirectory() as t:
            controller=ConnectionController(engine,CredentialStore(Path(t)/'creds'),client_factory=DemoBroker,clock=lambda:retry_clock[0])
            try:
                controller.configure('fixture','fixture','http://localhost/')
                controller.tokens=TokenBundle('fixture','fixture',datetime.now(timezone.utc)+timedelta(hours=1))
                controller.load_accounts();wait_for(lambda:finished(controller))
                controller.connect(123);wait_for(lambda:finished(controller))
                wait_for(lambda:engine.snapshot().counts['history_ready']==3)
                stream=created[-1]
                def tick(broker,price):
                    broker.emit(items[2],price,clock())
                    wait_for(lambda:any(r.key=='STOCK' and r.price==price for r in engine.snapshot().groups['Shares']))
                tick(stream,99.9);clock.advance(1);tick(stream,100.1)
                wait_for(lambda:engine.snapshot().counts['ranked']==1)
                bars.append(Candle(BUCKET,100,100.2,99.8,100.1))
                clock.value=BUCKET+timedelta(minutes=5,seconds=1);tick(stream,100.12)
                wait_for(lambda:engine.book.candidates.get('STOCK').status=='CONFIRMED')
                stream.callback('disconnected','remote_closed')
                wait_for(lambda:engine.connection_state=='interrupted');controller.poll()
                self.assertEqual(engine.snapshot().counts['ranked'],0)
                bars.append(Candle(BUCKET+timedelta(minutes=5),100.1,100.2,98.8,99))
                clock.value=BUCKET+timedelta(minutes=10,seconds=1)
                retry_clock[0]=2.1;controller.poll();wait_for(lambda:finished(controller))
                wait_for(lambda:engine.snapshot().counts['history_ready']==3)
                tick(created[-1],99.2)
                self.assertEqual(engine.snapshot().counts['ranked'],0)
                self.assertNotIn('STOCK',engine.book.candidates)
                self.assertIsNot(created[-1],stream)
                self.assertTrue(stream.closed)
                stream.emit(items[2],999,clock());time.sleep(.03)
                self.assertNotEqual(engine.snapshot().groups['Shares'][0].price,999)
            finally:controller.close();engine.close()

if __name__=='__main__':unittest.main()

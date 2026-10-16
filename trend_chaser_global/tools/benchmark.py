"""Exercise the real queue with 210 synthetic instruments and 420 transitions."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from global_trend.engine import Engine
from global_trend.models import Candle
from global_trend.catalog import CatalogEntry,ResolvedAsset,GROUPS
from global_trend.calendar import MarketCalendar
from global_trend.ctrader import Quote


def wait_for(predicate,timeout=8):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>end:raise AssertionError('Synthetic processing did not complete.')
        time.sleep(.005)


def run():
    class Clock:
        now=datetime(2026,10,15,13,34,57,tzinfo=timezone.utc)
        def __call__(self):return self.now
    clock=Clock();bucket=clock.now.replace(minute=30,second=0)
    calendar=MarketCalendar([(0,604800)],'UTC')
    items=[ResolvedAsset(CatalogEntry(f'TEST{i:03}',GROUPS[i%3],f'TEST{i:03}',f'TEST{i:03}',True),
                         i+1,2,calendar) for i in range(210)]
    class Source:
        account_id=1
        def __init__(self):
            self.bars=[Candle(bucket-timedelta(minutes=5*(100-i)),100,100.2,99.8,100,1) for i in range(100)]
        def history(self,*args):return list(self.bars)
        def subscribe_assets(self,assets,callback):self.callback=callback
        def close(self):pass
    class Recorder:
        def __init__(self):self.sent={};self.latencies=[];self.states=[]
        def write(self,event):
            if event.state in ('TREND_ADDED','TREND_CONFIRMED'):
                self.latencies.append(time.perf_counter()-self.sent[(event.symbol,event.state)])
                self.states.append(event.state)
        def close(self):pass
    rec=Recorder();source=Source()
    engine=Engine(clock=clock,logger=rec,entries=[a.entry for a in items])
    try:
        engine.connect(source,items)
        wait_for(lambda:engine.snapshot().counts['history_ready']==210)
        start=time.perf_counter()
        for item in items:source.callback('quote',Quote(item.symbol_id,99.9,None,clock()))
        clock.now+=timedelta(seconds=1)
        for item in items:
            rec.sent[(item.entry.olymp_name,'TREND_ADDED')]=time.perf_counter()
            source.callback('quote',Quote(item.symbol_id,100.1,None,clock()))
        wait_for(lambda:rec.states.count('TREND_ADDED')==210)
        for item in items:rec.sent[(item.entry.olymp_name,'TREND_CONFIRMED')]=time.perf_counter()
        source.bars.append(Candle(bucket,100,100.2,99.8,100.1,1))
        clock.now+=timedelta(seconds=3)
        for item in items:source.callback('quote',Quote(item.symbol_id,100.12,None,clock()))
        wait_for(lambda:rec.states.count('TREND_CONFIRMED')==210)
        values=sorted(rec.latencies)
        if len(values)!=420:raise AssertionError('Missing synthetic transitions.')
        result={'instruments':210,'transitions':420,'seconds':round(time.perf_counter()-start,4),
                'processing_p99_ms':round(values[int(.99*(len(values)-1))]*1000,3),
                'processing_max_ms':round(max(values)*1000,3),
                'scope':'synthetic queue and history; excludes broker/network/native Windows rendering'}
        if result['processing_p99_ms']>=1000:raise AssertionError(result)
        return result
    finally:engine.close()


if __name__=='__main__':print(json.dumps(run(),indent=2))

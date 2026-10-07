"""Synthetic 210-stock burst through the real processing queue; no broker credentials."""
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ema_scanner.models import Candle, Instrument, IST, Settings
from ema_scanner.broker import FeedQuote
from ema_scanner.scanner import Scanner


def run():
    now=datetime(2026,10,5,10,30,tzinfo=IST)
    times=[]
    for day,count in [(1,75),(2,75),(5,15)]:
        start=now.replace(day=day,hour=9,minute=15)
        times.extend(start+timedelta(minutes=5*i) for i in range(count))
    bars=[]
    for i,t in enumerate(times):
        price=100-max(0,i-145)*.002
        bars.append(Candle(t,price,price+.1,price-.1,price,10))
    inst=[Instrument(f'STOCK{i:03}',str(i)) for i in range(210)]
    class Recorder:
        def __init__(self): self.latency=[];self.sent={};self.crossed=0
        def write(self,e):
            if e.state in ('ARMED','CROSSED'):
                self.latency.append(time.perf_counter()-self.sent[(e.symbol,e.state)])
                if e.state=='CROSSED': self.crossed+=1
        def close(self): pass
    rec=Recorder()
    s=Scanner(Settings(),clock=lambda:now,start_worker=False,logger=rec)
    s.generation=1;s._process('universe',(inst,[]),1);s._process('status','open',1);s.market_status='NORMAL_OPEN'
    for i in inst: s._process('history',(i.key,s.epoch,0,bars,None),1)
    h=s.states['0'].history
    crossing=(h.ema21[-1]*10/11-h.ema9[-1]*.8)/(.2-1/11)
    worker=threading.Thread(target=s._run,daemon=True);worker.start()
    start=time.perf_counter()
    for state,price in [('ARMED',crossing-.001),('CROSSED',crossing+.001)]:
        for i in inst:
            rec.sent[(i.symbol,state)]=time.perf_counter()
            s._enqueue('feed',{'type':'live_feed','currentTs':int(now.timestamp()*1000),
                              'feeds':{i.key:{'ltpc':{'ltp':price,'ltt':int(now.timestamp()*1000)}}}},1)
    deadline=time.perf_counter()+5
    while rec.crossed<210 and time.perf_counter()<deadline: time.sleep(.01)
    elapsed=time.perf_counter()-start
    s.close();worker.join(timeout=2)
    if len(rec.latency)!=420 or rec.crossed!=210:
        raise AssertionError(f'Missing signals: events={len(rec.latency)}, crosses={rec.crossed}')
    lat=sorted(rec.latency)
    result={'stocks':210,'transitions':420,'seconds':round(elapsed,4),
            'quote_to_event_p99_ms':round(lat[int(.99*(len(lat)-1))]*1000,3),
            'quote_to_event_max_ms':round(max(lat)*1000,3),'scope':'synthetic cloud worker; excludes broker/network/Windows rendering'}
    if result['quote_to_event_p99_ms']>=1000: raise AssertionError(result)
    return result


if __name__=='__main__': print(json.dumps(run(),indent=2))

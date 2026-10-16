"""Fictional offline fixtures; never connect, read preferences or retain signals."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import MappingProxyType
from html import escape
import math
from .catalog import GROUPS,default_catalog
from .engine import DashboardState,DisplayRow
from .models import Candle,Instrument,Settings
from .indicators import EMAHistory


def make_demo_state():
    now=datetime(2026,10,15,14,32,tzinfo=timezone.utc);groups={g:[] for g in GROUPS}
    for entry in default_catalog():
        n=len(groups[entry.group]);side='LONG' if n%2==0 else 'SHORT';sign=1 if side=='LONG' else -1
        base=(1.12 if 'JPY' not in entry.key else 150) if entry.group=='Forex' else 200 if entry.group=='Shares' else 8000
        candles=[]
        for i in range(120):
            value=base*(1+.0005*math.sin(i/5)+sign*.00008*i)
            candles.append(Candle(now.replace(minute=30)-timedelta(minutes=5*(120-i)),value,value*1.0002,value*.9998,value))
        history=EMAHistory(candles,Instrument(entry.olymp_name,entry.key))
        snap=history.snapshot(candles[-1].close*(1+sign*.0002),now,Settings())
        angle=sign*(46-n*2.4)
        groups[entry.group].append(DisplayRow(entry.key,entry.olymp_name,entry.group,entry.ctrader_name,
            verified=True,rank=n+1,side=side,status='PROVISIONAL' if n==1 else 'CONFIRMED',
            captured_angle=angle,current_angle=snap.angle,price=snap.price,quote_time=now,
            signal_time=now-timedelta(minutes=5*(n+1)),ema9=snap.ema9,ema21=snap.ema21,
            distance_pct=100*(snap.price-snap.ema9)/snap.ema9,
            reason='Fictional sample for layout only',snapshot=snap))
    return DashboardState(MappingProxyType({g:tuple(rows) for g,rows in groups.items()}),False,
        'OFFLINE SAMPLE · fictional values',MappingProxyType({'mapped':20,'history_ready':20,'fresh':20,'ranked':20}),
        source='OFFLINE SAMPLE · no market connection',sample=True)


class DemoEngine:
    def __init__(self):self.closed=False;self._state=make_demo_state()
    def snapshot(self):return self._state
    def connect(self,*a,**kw):raise RuntimeError('Offline samples cannot connect to a broker.')
    def disconnect(self):pass
    def close(self):self.closed=True


def write_preview(path):
    state=make_demo_state();parts=[]
    for group,rows in state.groups.items():
        body=''.join(f'<tr class="{r.side}"><td>{r.rank:02d}</td><td><b>{escape(r.name)}</b><small>{escape(r.ctrader_name)}</small></td><td>{r.side}</td><td>{r.status}</td><td>{r.captured_angle:+.1f}°</td><td>{r.current_angle:+.1f}°</td><td>{r.price:,.5f}</td></tr>' for r in rows)
        parts.append(f'<section><h2>{group}<span>{len(rows)} instruments</span></h2><table><thead><tr><th>#</th><th>Instrument</th><th>Trend</th><th>State</th><th>Cross EMA9 ∠</th><th>Now ∠</th><th>Sample price</th></tr></thead><tbody>{body}</tbody></table></section>')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trend Chaser Global · Offline preview</title><style>
    *{box-sizing:border-box}body{margin:0;background:#0b1220;color:#e5edf8;font:15px system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:35px}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:30px;margin:0}p,small{color:#91a3ba}small{display:block;font-size:11px;margin-top:5px}.badge{border:1px solid #f1bd60;color:#f1bd60;padding:10px;border-radius:20px}aside{background:#142236;padding:20px;margin:25px 0;border-left:3px solid #35dbb4}section{margin:24px 0;border:1px solid #283950;border-radius:14px;overflow:hidden;background:#101d2e}h2{margin:0;padding:18px 22px;font-size:20px}h2 span{float:right;color:#91a3ba;font-size:12px;font-weight:400}table{width:100%;border-collapse:collapse}th{text-align:left;background:#1a2a40;color:#9baec6;font-size:11px;letter-spacing:.04em;padding:12px 20px}td{padding:13px 20px;border-top:1px solid #203047}.LONG{color:#59e6b5}.SHORT{color:#ff8993}td:nth-child(2){color:#e5edf8}footer{color:#91a3ba;padding:20px 0;font-size:12px}@media(max-width:800px){main{padding:15px}section{overflow:auto}th,td{padding:10px;white-space:nowrap}header{display:block}.badge{display:inline-block;margin-top:15px}}
    </style><main><header><div><h1>◉ Trend Chaser <span style="color:#35dbb4">Global</span></h1><p>Follow the trend. Keep the signal in view.</p></div><div class="badge">OFFLINE SAMPLE</div></header><aside>5 minute candles · EMA9 / EMA21 · Each section ranks by frozen crossover strength.<br><small>All prices and trends below are fictional. Live mode uses verified cTrader demo mappings.</small></aside>'''+''.join(parts)+'''<footer>Manual trading on Olymp Trade · Quotes may differ between platforms · Higher volatility increases losses as well as opportunities. This preview provides no trading advice.</footer></main></html>'''
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(html,encoding='utf-8')

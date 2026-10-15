"""Offline runtime, dependencies, protocol and real Tk startup checks."""
from datetime import datetime,timedelta,timezone
import argparse,struct,sys

def verify(no_display=False):
    import requests,certifi,tkinter,tzdata
    from zoneinfo import ZoneInfo
    from global_trend.protocol import OA,encode_message,decode_message
    from global_trend.models import Candle,Instrument,Settings
    from global_trend.indicators import EMAHistory
    from global_trend.ui import App
    if sys.version_info<(3,12) or struct.calcsize('P')!=8:raise RuntimeError('Python 3.12+ x64 is required.')
    now=datetime(2026,10,15,12,tzinfo=timezone.utc)
    bars=[Candle(now-timedelta(minutes=5*(100-i)),100,101,99,100) for i in range(100)]
    snap=EMAHistory(bars,Instrument('TEST','TEST')).snapshot(101,now,Settings())
    if abs(snap.ema9-100.2)>1e-10:raise RuntimeError('EMA check failed.')
    message=OA.ProtoOAApplicationAuthReq(clientId='offline',clientSecret='sample')
    ident,decoded=decode_message(encode_message(message,'offline'))
    if ident!='offline' or decoded.clientId!='offline':raise RuntimeError('Protocol check failed.')
    ZoneInfo('America/New_York')
    if not no_display:
        root=tkinter.Tk();root.withdraw();root.update();root.destroy()
    print('Offline installation checks passed: Python x64, dependencies, cTrader protocol, EMA, time zones'+(' and Tk.' if not no_display else '.'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-display',action='store_true');verify(parser.parse_args().no_display)

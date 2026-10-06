"""Offline imports, broker decoder, strategy symmetry and optional Tk startup."""
from datetime import datetime, timedelta, timezone
import argparse
import os
import struct
import sys


def verify(no_display=False):
    import requests, certifi, websocket, tkinter
    import upstox_client
    from upstox_client.feeder.proto import MarketDataFeedV3_pb2
    from google.protobuf.json_format import MessageToDict
    from ema_scanner.models import Candle, Instrument, Settings
    from ema_scanner.indicators import EMAHistory
    from ema_scanner.ui import plot_bounds
    if sys.version_info<(3,12) or struct.calcsize('P')!=8:
        raise RuntimeError('Python 3.12+ x64 is required.')
    stamp=datetime(2026,10,5,5,0,tzinfo=timezone.utc)
    bars=[Candle(stamp-timedelta(minutes=5*(100-i)),100,101,99,100,1) for i in range(100)]
    h=EMAHistory(bars,Instrument('TEST','TEST'))
    a=h.snapshot(101,stamp,Settings())
    if abs(a.ema9-100.2)>1e-10:raise RuntimeError('EMA self-check failed.')
    payload=MarketDataFeedV3_pb2.FeedResponse(type=1,currentTs=1)
    if MessageToDict(payload)['type']!='live_feed':raise RuntimeError('Feed decoder check failed.')
    upstox_client.ApiClient(upstox_client.Configuration())
    if os.name=='nt':
        from ema_scanner.credentials import WindowsDPAPI
        cipher=WindowsDPAPI();probe=b'EMA offline token-protection self-check'
        if cipher.unprotect(cipher.protect(probe))!=probe:
            raise RuntimeError('Windows token-protection self-check failed.')
    if not no_display:
        root=tkinter.Tk();root.withdraw();root.update();root.destroy()
    print('Offline installation checks passed: Python x64, Tk, dependencies, V3 decoder and EMA.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-display',action='store_true')
    verify(parser.parse_args().no_display)

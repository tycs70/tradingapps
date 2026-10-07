"""Offline runtime, trend, sample UI and synthetic token-protection checks.

Never loads saved credentials, connects a broker or writes user data.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import struct
import sys
import tempfile


def require(value, message):
    if not value:raise RuntimeError(message)


def verify(no_display=False):
    # Select the private Tcl/Tk libraries before initializing Tk, including -E.
    runtime=Path(sys.executable).resolve().parent
    if (runtime/'tcl'/'tcl8.6').is_dir() and (runtime/'tcl'/'tk8.6').is_dir():
        os.environ['TCL_LIBRARY']=str(runtime/'tcl'/'tcl8.6')
        os.environ['TK_LIBRARY']=str(runtime/'tcl'/'tk8.6')
    import requests, certifi, websocket, tkinter
    import upstox_client
    from upstox_client.feeder.proto import MarketDataFeedV3_pb2
    from google.protobuf.json_format import MessageToDict
    from ema_scanner.models import Candle, Instrument, Settings
    from ema_scanner.indicators import EMAHistory
    from ema_scanner import VERSION
    from ema_scanner.demo import OfflineScanner, sample_data, render_html, LABEL
    from ema_scanner.trends import TrendBook
    from ema_scanner.credentials import TokenStore, WindowsDPAPI
    from ema_scanner.index_universe import parse_constituents, select_niftynext50
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
    require(VERSION=='1.0.0','Unexpected app version.')
    index_csv='Company Name,Industry,Symbol,Series,ISIN Code\n'+ '\n'.join(
        f'Test {i},Test,NIFTYTEST{i:02},EQ,INE{i:09}' for i in range(50))
    members=parse_constituents(index_csv)
    master=[]
    for i in range(51):
        isin=f'INE{i:09}';key='NSE_EQ|'+isin
        master.append(dict(segment='NSE_EQ',instrument_type='EQ',instrument_key=key,
                           trading_symbol=f'NIFTYTEST{i:02}',isin=isin))
        master.append(dict(segment='NSE_FO',instrument_type='CE',underlying_type='EQUITY',
                           underlying_key=key,underlying_symbol=f'NIFTYTEST{i:02}',
                           expiry=(stamp.date()+timedelta(days=30)).isoformat()))
    stocks,reasons=select_niftynext50(master,stamp.date(),members)
    require(len(stocks)==50 and {stock.symbol for stock in stocks}==set(members.values())
            and not reasons,'Nifty Next 50 universe boundary check failed.')
    samples=sample_data()
    require(samples['status']==LABEL and not samples['connected'],'Sample identity check failed.')
    require(len(samples['trends_long'])==len(samples['trends_short'])==7,'Sample Top 7 check failed.')
    require(len(samples['armed'])==3,'Sample pre-cross check failed.')
    offline=OfflineScanner()
    offline.connect('offline-synthetic-probe')
    state=offline.snapshot()
    require(not state['connected'] and not any(state[k] for k in ('trends_long','trends_short','armed','rows')),
            'Demo contaminated live membership.')
    sheet=Path(__file__).resolve().parent/'demo.html'
    require(sheet.read_text(encoding='utf-8')==render_html(),'Packaged demo sheet is out of date.')
    # Mirrored real registry rules, using fictional immutable samples only.
    for side,name in (('LONG','trends_long'),('SHORT','trends_short')):
        sign=1 if side=='LONG' else -1
        snapshot=samples[name][0].snapshot
        book=TrendBook(snapshot.quote_time.date())
        before=replace(snapshot,ema9=snapshot.ema21-sign)
        require(not book.observe(before,initial=True),'Initial history invented a trend.')
        added=book.observe(snapshot)
        require(len(added)==1 and added[0].action=='ADD','Observed crossover was not added.')
        frozen=book.candidates[snapshot.key].crossover_angle
        changed=replace(snapshot,angle=sign*.5)
        book.observe(changed)
        require(book.top(side,{snapshot.key:changed})[0].crossover_angle==frozen,'Crossover rank changed.')
        bar=Candle(snapshot.bucket,snapshot.ema9,snapshot.ema9+20,snapshot.ema9-20,
                   snapshot.ema9+sign,1)
        confirmed=book.verified_candle(snapshot.key,bar,snapshot.ema9,snapshot.ema21)
        require(len(confirmed)==1 and confirmed[0].action=='CONFIRM','Completed crossing candle did not confirm.')
        touch=replace(bar,time=bar.time+timedelta(minutes=5),close=snapshot.ema9)
        require(not book.verified_candle(snapshot.key,touch,snapshot.ema9,snapshot.ema21)
                and snapshot.key in book.candidates,'Wick/equality removed confirmed membership.')
        adverse=replace(touch,time=touch.time+timedelta(minutes=5),close=snapshot.ema9-sign)
        removed=book.verified_candle(snapshot.key,adverse,snapshot.ema9,snapshot.ema21)
        require(len(removed)==1 and removed[0].action=='REMOVE','Adverse close did not remove membership.')
        require(not book.observe(snapshot) and not book.candidates,'Removed trend revived without a crossover.')
    # Disposable synthetic probe, never a real user access token. Native Windows
    # must pass user-scoped DPAPI roundtrip and damaged-blob rejection.
    with tempfile.TemporaryDirectory(prefix='trend-chase-offline-') as temp:
        token=TokenStore(Path(temp)/'probe'/'token.dpapi')
        probe='TrendChaseOfflineSyntheticProbe'
        if os.name=='nt':
            require(WindowsDPAPI.available,'Native Windows protection unavailable.')
            token.save(probe)
            require(token.load()==probe,'Windows DPAPI roundtrip failed.')
            require(probe.encode() not in token.path.read_bytes(),'Token was stored as plaintext.')
            token.path.write_bytes(token.path.read_bytes()[:-1])
            try:token.load()
            except OSError:pass
            else:raise RuntimeError('Windows DPAPI accepted a damaged probe.')
            token.clear()
            dpapi='passed'
        else:
            require(not token.available,'Unexpected native security platform.')
            try:token.save(probe)
            except OSError:pass
            else:raise RuntimeError('Non-Windows token persistence silently succeeded.')
            require(not token.path.parent.exists(),'Unavailable DPAPI created a plaintext fallback.')
            dpapi='unavailable on this platform; no plaintext fallback'
        if not no_display:
            from ema_scanner.storage import SettingsStore
            from ema_scanner.ui import App
            root=tkinter.Tk();root.withdraw()
            app=None
            try:
                settings_path=Path(temp)/'never-written'/'settings.json'
                app=App(root,offline,SettingsStore(settings_path),demo_mode=True)
                root.update()
                require(root.title().startswith('Trend Chaser Nifty Next 50'),'Unexpected desktop app identity.')
                require(len(app.demo_bullish_board.get_children())==7 and
                        len(app.demo_bearish_board.get_children())==7,'Tk sample tables did not render.')
                require(not app.show_chart.get() and not app.demo_show_chart.get(),'Charts are not hidden by default.')
                require(not settings_path.parent.exists(),'Offline demo wrote live settings.')
            finally:
                if app:app.close()
                else:
                    offline.close()
                    root.destroy()
    report={'app':'Trend Chaser Nifty Next 50','version':VERSION,'python_x64':'passed','dependencies':'passed',
            'feed_decoder':'passed','ema':'passed','niftynext50_universe':'passed',
            'trend_lifecycle':'passed','offline_demo':'passed',
            'tk':'not run (--no-display)' if no_display else 'passed','dpapi':dpapi}
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-display',action='store_true')
    verify(parser.parse_args().no_display)

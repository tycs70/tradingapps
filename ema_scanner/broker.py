"""Upstox REST and V3 streaming boundary. Error messages deliberately omit bodies/URLs."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import gzip
import json
import math
import ssl
import threading
import time
from urllib.parse import quote

import requests
import certifi
import websocket

from .history import parse_candles, parse_time, validate_history
from .models import Candle, IST
from .universe import eligible_stocks

MASTER_URL = 'https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz'


def normalize_token(token: str) -> str:
    value = token.strip()
    if value.lower().startswith('bearer '):
        value = value[7:].strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError('Paste a current Upstox access token without line breaks.')
    return value


class RateLimiter:
    def __init__(self, interval=.25, clock=time.monotonic, sleeper=time.sleep):
        self.interval,self.clock,self.sleeper = interval,clock,sleeper
        self.lock = threading.Lock()
        self.next = 0

    def wait(self):
        with self.lock:
            now = self.clock()
            delay = max(0,self.next-now)
            if delay:
                self.sleeper(delay)
            self.next = max(now,self.next)+self.interval


@dataclass(frozen=True)
class FeedQuote:
    key: str
    price: float
    time: datetime
    message_time: datetime
    initial: bool = False


def _find(node: dict, name: str):
    if name in node:
        return node[name]
    for value in node.values():
        if isinstance(value,dict):
            found = _find(value,name)
            if found is not None:
                return found
    return None


def parse_feed(message: dict) -> tuple[list[FeedQuote], dict[str,list[Candle]], str | None]:
    stamp = parse_time(message['currentTs'])
    status = message.get('marketInfo',{}).get('segmentStatus',{}).get('NSE_EQ')
    quotes, minutes = [], {}
    initial = message.get('type') not in ('live_feed',1,'1')
    for key,node in message.get('feeds',{}).items():
        if not isinstance(node,dict):
            continue
        ltpc = _find(node,'ltpc')
        if ltpc:
            try:
                quotes.append(FeedQuote(key,float(ltpc['ltp']),parse_time(ltpc['ltt']),stamp,initial))
            except (KeyError,ValueError,TypeError,OverflowError,OSError):
                pass
        ohlc = _find(node,'marketOHLC')
        if ohlc:
            for row in ohlc.get('ohlc',[]):
                if row.get('interval') == 'I1':
                    c = Candle(parse_time(row['ts']),float(row['open']),float(row['high']),
                               float(row['low']),float(row['close']),float(row.get('vol',0)))
                    if not c.valid():
                        raise ValueError('Invalid stream minute OHLC.')
                    minutes.setdefault(key,[]).append(c)
    return quotes,minutes,status


class Broker:
    def __init__(self, token: str, get=requests.get):
        self._token = normalize_token(token)
        self._get = get
        self._rate = RateLimiter()
        self._stop = threading.Event()
        self._stream = None

    def _json(self, url: str) -> dict:
        for attempt in range(3):
            if self._stop.is_set():
                raise RuntimeError('Connection cancelled.')
            self._rate.wait()
            try:
                r = self._get(url,headers={'Accept':'application/json','Authorization':'Bearer '+self._token},timeout=(5,20))
            except requests.RequestException:
                if attempt < 2:
                    if self._stop.wait(.5*(attempt+1)): break
                    continue
                raise RuntimeError('Upstox request failed; check the network.') from None
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < 2:
                    if self._stop.wait(1.5*(attempt+1)): break
                    continue
            if r.status_code != 200:
                raise RuntimeError(f'Upstox HTTP {r.status_code}; check access token or account permissions.')
            try:
                payload = r.json()
                if payload.get('status') != 'success':
                    raise ValueError()
                return payload
            except (ValueError,AttributeError):
                raise RuntimeError('Unexpected Upstox response.') from None
        raise RuntimeError('Connection cancelled.')

    def universe(self):
        try:
            response = self._get(MASTER_URL,timeout=(5,30))
            if response.status_code != 200:
                raise ValueError()
            master = json.loads(gzip.decompress(response.content))
        except (requests.RequestException,ValueError,OSError):
            raise RuntimeError('Unable to download the current NSE instrument master.') from None
        instruments,reasons = eligible_stocks(master,datetime.now(IST).date())
        if not instruments:
            raise RuntimeError('No current stock-option underlyings resolved.')
        return instruments,reasons

    def history(self, key: str, now: datetime) -> list[Candle]:
        encoded = quote(key,safe='')
        end = now.date()-timedelta(days=1)
        start = now.date()-timedelta(days=14)
        root = 'https://api.upstox.com/v3/historical-candle/'
        rows = self._json(f'{root}{encoded}/minutes/5/{end.isoformat()}/{start.isoformat()}')['data']['candles']
        rows += self._json(f'{root}intraday/{encoded}/minutes/5')['data']['candles']
        candles = parse_candles(rows,now)
        validate_history(candles,now)
        return candles

    def stream(self, keys, message, status):
        # SDK 2.23.0's feeder sets CERT_NONE. Use its protobuf decoder with
        # our own verified transport rather than inheriting that behavior.
        url = self._json('https://api.upstox.com/v3/feed/market-data-feed/authorize')['data']['authorized_redirect_uri']
        if not url.startswith('wss://'):
            raise RuntimeError('Upstox returned an invalid secure feed address.')
        self._stream = SecureStream(url,keys,message,status)
        def run():
            try:
                if not self._stop.is_set(): self._stream.run()
            except Exception:
                status('error')
        threading.Thread(target=run,name='upstox-stream',daemon=True).start()

    def disconnect(self):
        self._stop.set()
        if self._stream:
            try: self._stream.disconnect()
            except Exception: pass
        self._token = ''


class SecureStream:
    def __init__(self, url, keys, message, status, factory=websocket.WebSocketApp):
        self.url,self.keys,self.message,self.status,self.factory = url,keys,message,status,factory
        self.stop = threading.Event()
        self.ws = None

    def on_open(self, ws):
        if self.stop.is_set():
            ws.close()
            return
        self.status('open')
        request = {'guid':'ema-pre-cross','method':'sub','data':{'instrumentKeys':self.keys,'mode':'full'}}
        ws.send(json.dumps(request).encode('utf-8'),opcode=websocket.ABNF.OPCODE_BINARY)

    def on_message(self, ws, data):
        if self.stop.is_set(): return
        try:
            from upstox_client.feeder.proto import MarketDataFeedV3_pb2
            from google.protobuf.json_format import MessageToDict
            self.message(MessageToDict(MarketDataFeedV3_pb2.FeedResponse.FromString(data)))
        except Exception:
            self.status('invalid')

    def run_once(self):
        if self.stop.is_set(): return
        self.ws = self.factory(self.url,on_open=self.on_open,on_message=self.on_message,
                               on_error=lambda *args:self.status('error'),
                               on_close=lambda *args:self.status('closed'))
        self.ws.run_forever(sslopt={'cert_reqs':ssl.CERT_REQUIRED,'check_hostname':True,
                                   'ca_certs':certifi.where()},ping_interval=20,ping_timeout=10)

    def run(self):
        for attempt in range(21):
            if self.stop.is_set(): break
            self.run_once()
            if self.stop.wait(5): break
        if not self.stop.is_set(): self.status('stopped')

    def disconnect(self):
        self.stop.set()
        if self.ws: self.ws.close()
        self.url = ''

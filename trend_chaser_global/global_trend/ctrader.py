"""Spotware demo market data boundary; no order operations are implemented."""
from dataclasses import dataclass,replace
from collections import OrderedDict
from datetime import datetime,timedelta,timezone,date
import threading
import time
from google.protobuf.json_format import MessageToDict
from .protocol import OA,Model
from .transport import ProtoClient,TransportError,AuthorizationError
from .models import Candle
from .calendar import MarketCalendar
from .catalog import resolve_catalog

UTC=timezone.utc


@dataclass(frozen=True)
class Quote:
    symbol_id:int
    bid:float|None
    ask:float|None
    time:datetime


def decode_spot(message):
    if not message.HasField('timestamp'):
        raise ValueError('Quote has no source timestamp.')
    bid=message.bid/100000 if message.HasField('bid') else None
    ask=message.ask/100000 if message.HasField('ask') else None
    if (bid is not None and bid<=0) or (ask is not None and ask<=0):
        raise ValueError('Invalid quote price.')
    return Quote(message.symbolId,bid,ask,datetime.fromtimestamp(message.timestamp/1000,UTC))


def decode_candles(message,now):
    if message.period!=Model.M5:raise ValueError('Five-minute history is required.')
    rows={}
    for bar in message.trendbar:
        if not bar.HasField('utcTimestampInMinutes'):
            raise ValueError('Candle has no source timestamp.')
        stamp=datetime.fromtimestamp(bar.utcTimestampInMinutes*60,UTC)
        if stamp.minute%5:raise ValueError('Candle is not five-minute aligned.')
        candle=Candle(stamp,(bar.low+bar.deltaOpen)/100000,(bar.low+bar.deltaHigh)/100000,
                      bar.low/100000,(bar.low+bar.deltaClose)/100000,bar.volume)
        if not candle.valid():raise ValueError('Invalid historical OHLC.')
        if stamp+timedelta(minutes=5)<=now:rows[stamp]=candle
    return sorted(rows.values(),key=lambda b:b.time)


def symbol_calendar(symbol):
    rules=[]
    for h in symbol.holiday:
        rules.append({'date':date(1970,1,1)+timedelta(days=h.holidayDate),
                      'zone':h.scheduleTimeZone,'recurring':h.isRecurring,
                      'start':h.startSecond if h.HasField('startSecond') else 0,
                      'end':h.endSecond if h.HasField('endSecond') else 86400})
    return MarketCalendar([(p.startSecond,p.endSecond) for p in symbol.schedule],
                          symbol.scheduleTimeZone or 'UTC',holiday_rules=rules)


class CTraderClient:
    def __init__(self,client_id,client_secret,transport=None):
        self._client_id=client_id;self._client_secret=client_secret
        self.transport=transport or ProtoClient()
        self._account_id=None;self._opened=False;self._closed=threading.Event()
        self._history_lock=threading.Lock();self._next_history=0;self._callback=None
        self._bar_versions=OrderedDict()
        self.transport.subscribe(self._event)

    @property
    def account_id(self):return self._account_id

    def open(self):
        if not self._opened:
            self.transport.request(OA.ProtoOAApplicationAuthReq(clientId=self._client_id,clientSecret=self._client_secret))
            self._opened=True

    @staticmethod
    def _token(tokens):return tokens.access_token if hasattr(tokens,'access_token') else tokens

    def accounts(self,tokens):
        self.open()
        response=self.transport.request(OA.ProtoOAGetAccountListByAccessTokenReq(accessToken=self._token(tokens)))
        return tuple({'account_id':int(a.ctidTraderAccountId),'login':int(a.traderLogin),
                      'is_live':bool(a.isLive) if a.HasField('isLive') else None,
                      'broker':a.brokerTitleShort} for a in response.ctidTraderAccount)

    def authorize(self,account_id,tokens):
        account=next((a for a in self.accounts(tokens) if a['account_id']==account_id),None)
        if account is None or account['is_live'] is not False:
            raise AuthorizationError('Select an explicitly identified authorized demo account.')
        response=self.transport.request(OA.ProtoOAAccountAuthReq(ctidTraderAccountId=account_id,
                                                                 accessToken=self._token(tokens)))
        if response.ctidTraderAccountId!=account_id:raise TransportError('Account authentication mismatch.')
        self._account_id=account_id

    def _account(self):
        if self._account_id is None:raise TransportError('Authorize a demo account first.')
        return self._account_id

    def catalog(self):
        response=self.transport.request(OA.ProtoOASymbolsListReq(ctidTraderAccountId=self._account()))
        return [dict(MessageToDict(s,preserving_proto_field_name=True),enabled=bool(s.enabled))
                for s in response.symbol]

    def resolve(self,entries):
        assets,reasons=resolve_catalog(entries,self.catalog())
        if not assets:return [],reasons
        response=self.transport.request(OA.ProtoOASymbolByIdReq(ctidTraderAccountId=self._account(),
                                                               symbolId=[a.symbol_id for a in assets]))
        symbols={s.symbolId:s for s in response.symbol};result=[]
        for asset in assets:
            symbol=symbols.get(asset.symbol_id)
            if symbol is None:
                reasons[asset.entry.key]='Broker metadata unavailable';continue
            try:calendar=symbol_calendar(symbol)
            except (ValueError,KeyError):
                reasons[asset.entry.key]='Invalid broker schedule';continue
            result.append(replace(asset,digits=symbol.digits,schedule=calendar))
        return result,reasons

    def history(self,asset,start,end):
        account=self._account();first=int(start.timestamp()*1000);last=int(end.timestamp()*1000)
        result={}
        for _ in range(40):
            if self._closed.is_set():raise TransportError('History loading cancelled.')
            with self._history_lock:
                if self._closed.wait(max(0,self._next_history-time.monotonic())):
                    raise TransportError('History loading cancelled.')
                self._next_history=time.monotonic()+.5
                response=self.transport.request(OA.ProtoOAGetTrendbarsReq(ctidTraderAccountId=account,
                    symbolId=asset.symbol_id,period=Model.M5,fromTimestamp=first,toTimestamp=last,count=500))
            for candle in decode_candles(response,end):
                if start<=candle.time<end:result[candle.time]=candle
            if not response.hasMore:break
            if not response.trendbar:raise TransportError('Incomplete history response.')
            earlier=min(b.utcTimestampInMinutes for b in response.trendbar)*60000-1
            if earlier>=last:raise TransportError('History pagination did not advance.')
            last=earlier
            if last<first:break
        else:raise TransportError('History page limit exceeded.')
        return sorted(result.values(),key=lambda c:c.time)

    def subscribe_assets(self,assets,callback):
        self._callback=callback;account=self._account()
        if not assets:return
        self.transport.request(OA.ProtoOASubscribeSpotsReq(ctidTraderAccountId=account,
            symbolId=[a.symbol_id for a in assets],subscribeToSpotTimestamp=True))
        for asset in assets:
            self.transport.request(OA.ProtoOASubscribeLiveTrendbarReq(ctidTraderAccountId=account,
                symbolId=asset.symbol_id,period=Model.M5))

    def _event(self,message):
        if not self._callback:return
        if isinstance(message,TransportError):self._callback('disconnected',message.code)
        elif isinstance(message,OA.ProtoOASpotEvent) and message.ctidTraderAccountId==self._account_id:
            if message.HasField('bid') or message.HasField('ask'):
                try:q=decode_spot(message)
                except (ValueError,OverflowError,OSError):pass
                else:self._callback('quote',q)
            if message.HasField('timestamp'):
                for bar in message.trendbar:
                    if bar.period!=Model.M5 or (bar.utcTimestampInMinutes+5)*60000>message.timestamp:continue
                    key=(message.symbolId,bar.utcTimestampInMinutes)
                    version=(bar.low,bar.deltaOpen,bar.deltaClose,bar.deltaHigh,bar.volume)
                    if self._bar_versions.get(key)!=version:
                        self._bar_versions[key]=version;self._bar_versions.move_to_end(key)
                        while len(self._bar_versions)>2048:self._bar_versions.popitem(last=False)
                        self._callback('bar_update',message.symbolId)
        elif isinstance(message,(OA.ProtoOAAccountDisconnectEvent,OA.ProtoOAClientDisconnectEvent)):
            self._callback('disconnected','server')
        elif isinstance(message,OA.ProtoOAAccountsTokenInvalidatedEvent) and self._account_id in message.ctidTraderAccountIds:
            self._callback('disconnected','authorization')

    def close(self):
        self._closed.set();self.transport.close();self._client_secret=''
        self._opened=False;self._account_id=None

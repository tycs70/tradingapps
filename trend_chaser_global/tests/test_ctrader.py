from datetime import datetime,timedelta,timezone
import unittest
from global_trend.catalog import default_catalog
from global_trend.protocol import OA,Model,encode_message,decode_message
from global_trend.ctrader import CTraderClient
from global_trend.transport import TransportError

UTC=timezone.utc


class ProtocolPeer:
    """A stateful protocol peer; assertions concern public decoded results."""
    def __init__(self):self.callback=None;self.closed=False;self.known_live=True
    def subscribe(self,callback):self.callback=callback
    def close(self):self.closed=True
    def request(self,message):
        _,m=decode_message(encode_message(message,'peer'))
        if isinstance(m,OA.ProtoOAApplicationAuthReq):return OA.ProtoOAApplicationAuthRes()
        if isinstance(m,OA.ProtoOAGetAccountListByAccessTokenReq):
            r=OA.ProtoOAGetAccountListByAccessTokenRes(accessToken='test-token')
            a=r.ctidTraderAccount.add(ctidTraderAccountId=123,traderLogin=5923508,brokerTitleShort='Spotware')
            if self.known_live:a.isLive=False
            r.ctidTraderAccount.add(ctidTraderAccountId=999,traderLogin=999,isLive=True)
            return r
        if isinstance(m,OA.ProtoOAAccountAuthReq):return OA.ProtoOAAccountAuthRes(ctidTraderAccountId=m.ctidTraderAccountId)
        if isinstance(m,OA.ProtoOASymbolsListReq):
            r=OA.ProtoOASymbolsListRes(ctidTraderAccountId=123)
            r.symbol.add(symbolId=941,symbolName='APPLE',enabled=True)
            return r
        if isinstance(m,OA.ProtoOASymbolByIdReq):
            r=OA.ProtoOASymbolByIdRes(ctidTraderAccountId=123)
            s=r.symbol.add(symbolId=941,digits=2,pipPosition=1,scheduleTimeZone='UTC')
            s.schedule.add(startSecond=0,endSecond=604800)
            return r
        if isinstance(m,OA.ProtoOAGetTrendbarsReq):
            r=OA.ProtoOAGetTrendbarsRes(ctidTraderAccountId=123,period=Model.M5,symbolId=941)
            r.trendbar.add(low=10000000,deltaOpen=10000,deltaClose=20000,deltaHigh=30000,
                          utcTimestampInMinutes=1000,volume=5)
            return r
        if isinstance(m,OA.ProtoOASubscribeSpotsReq):return OA.ProtoOASubscribeSpotsRes(ctidTraderAccountId=123)
        if isinstance(m,OA.ProtoOASubscribeLiveTrendbarReq):return OA.ProtoOASubscribeLiveTrendbarRes(ctidTraderAccountId=123)
        raise AssertionError(type(m).__name__)


class CTraderTest(unittest.TestCase):
    def setUp(self):
        self.peer=ProtocolPeer();self.client=CTraderClient('id','test-secret',transport=self.peer)
    def tearDown(self):self.client.close()
    def test_internal_account_id_is_distinct_from_visible_login(self):
        accounts=self.client.accounts('test-token')
        self.assertEqual(accounts[0]['account_id'],123)
        self.assertEqual(accounts[0]['login'],5923508)
        self.client.authorize(123,'test-token')
        self.assertEqual(self.client.account_id,123)
    def test_live_and_unknown_account_modes_are_rejected(self):
        with self.assertRaises(TransportError):self.client.authorize(999,'test-token')
        self.peer.known_live=False
        with self.assertRaises(TransportError):self.client.authorize(123,'test-token')
    def test_catalog_resolution_attaches_actual_precision_and_schedule(self):
        self.client.authorize(123,'test-token')
        entries=[e for e in default_catalog() if e.key in ('AAPL','CAT')]
        resolved,reasons=self.client.resolve(entries)
        self.assertEqual(len(resolved),1);self.assertEqual(resolved[0].symbol_id,941)
        self.assertEqual(resolved[0].digits,2)
        self.assertTrue(resolved[0].schedule.is_open(datetime.now(UTC)))
        self.assertIn('CAT',reasons)
    def test_history_produces_completed_valid_candles(self):
        self.client.authorize(123,'test-token')
        asset=self.client.resolve([default_catalog()[13]])[0][0]
        a=datetime.fromtimestamp(1000*60,UTC)
        rows=self.client.history(asset,a,a+timedelta(minutes=5))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].time,a)
        self.assertAlmostEqual(rows[0].close,100.2)
    def test_event_stream_rejects_other_account_and_keeps_quote_sides(self):
        self.client.authorize(123,'test-token')
        asset=self.client.resolve([default_catalog()[13]])[0][0];events=[]
        self.client.subscribe_assets([asset],lambda *args:events.append(args))
        for account in [999,123]:
            self.peer.callback(OA.ProtoOASpotEvent(ctidTraderAccountId=account,symbolId=941,
                                                ask=123456,timestamp=100000))
        self.assertEqual(len(events),1)
        self.assertEqual(events[0][0],'quote');self.assertIsNone(events[0][1].bid)

    def test_closed_bar_revision_notifies_engine_without_fabricating_bid(self):
        self.client.authorize(123,'test-token')
        asset=self.client.resolve([default_catalog()[13]])[0][0];events=[]
        self.client.subscribe_assets([asset],lambda *args:events.append(args))
        message=OA.ProtoOASpotEvent(ctidTraderAccountId=123,symbolId=941,timestamp=1005*60000)
        b=message.trendbar.add(period=Model.M5,low=10000000,deltaOpen=0,deltaClose=10,
                              deltaHigh=20,utcTimestampInMinutes=1000,volume=1)
        self.peer.callback(message);self.peer.callback(message)
        b.deltaClose=15;self.peer.callback(message)
        self.assertEqual(events,[('bar_update',941),('bar_update',941)])


if __name__=='__main__':unittest.main()

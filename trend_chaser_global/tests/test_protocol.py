from datetime import datetime, timezone
from dataclasses import replace
import unittest
from global_trend.protocol import OA, Model, Common, encode_message, decode_message
from global_trend.ctrader import decode_candles, decode_spot, symbol_calendar

UTC=timezone.utc


class ProtocolTest(unittest.TestCase):
    def test_official_auth_and_account_messages_roundtrip(self):
        messages=[OA.ProtoOAApplicationAuthReq(clientId='test-id',clientSecret='test-only-secret'),
                  OA.ProtoOAAccountAuthReq(ctidTraderAccountId=123,accessToken='test-only-token'),
                  OA.ProtoOAGetAccountListByAccessTokenReq(accessToken='test-only-token'),
                  OA.ProtoOASymbolsListReq(ctidTraderAccountId=123),
                  OA.ProtoOASubscribeSpotsReq(ctidTraderAccountId=123,symbolId=[99],subscribeToSpotTimestamp=True)]
        for m in messages:
            ident,parsed=decode_message(encode_message(m,'request-123'))
            self.assertEqual(ident,'request-123')
            self.assertEqual(parsed,m)

    def test_history_uses_price_deltas_and_utc_minutes(self):
        response=OA.ProtoOAGetTrendbarsRes(ctidTraderAccountId=12,period=Model.M5,symbolId=99)
        b=response.trendbar.add(low=123000,deltaOpen=20,deltaClose=30,deltaHigh=50,
                               volume=7,utcTimestampInMinutes=1000)
        rows=decode_candles(response,datetime.fromtimestamp(1005*60,UTC))
        self.assertEqual(len(rows),1)
        c=rows[0]
        self.assertAlmostEqual(c.low,1.23);self.assertAlmostEqual(c.open,1.2302)
        self.assertAlmostEqual(c.close,1.2303);self.assertAlmostEqual(c.high,1.2305)
        self.assertEqual(c.time,datetime.fromtimestamp(1000*60,UTC))
        self.assertEqual(decode_candles(response,datetime.fromtimestamp(1004*60,UTC)),[])

    def test_invalid_ohlc_and_non_m5_history_are_rejected(self):
        m=OA.ProtoOAGetTrendbarsRes(ctidTraderAccountId=12,period=Model.M5)
        m.trendbar.add(low=100,deltaHigh=1,deltaClose=20,utcTimestampInMinutes=1000,volume=1)
        with self.assertRaises(ValueError):decode_candles(m,datetime.fromtimestamp(2000*60,UTC))
        m.period=Model.M1
        with self.assertRaises(ValueError):decode_candles(m,datetime.now(UTC))

    def test_ask_only_quote_is_not_a_bid(self):
        m=OA.ProtoOASpotEvent(ctidTraderAccountId=12,symbolId=99,ask=123456,timestamp=100000)
        q=decode_spot(m)
        self.assertIsNone(q.bid);self.assertAlmostEqual(q.ask,1.23456)
        self.assertEqual(q.time,datetime.fromtimestamp(100,UTC))
        m.ClearField('timestamp')
        with self.assertRaises(ValueError):decode_spot(m)

    def test_broker_schedule_is_parsed(self):
        m=Model.ProtoOASymbol(symbolId=99,digits=5,pipPosition=4,scheduleTimeZone='UTC')
        m.schedule.add(startSecond=118800,endSecond=122400)
        cal=symbol_calendar(m)
        self.assertTrue(cal.is_open(datetime(2026,10,12,9,tzinfo=UTC)))
        self.assertFalse(cal.is_open(datetime(2026,10,12,10,tzinfo=UTC)))


if __name__=='__main__':unittest.main()

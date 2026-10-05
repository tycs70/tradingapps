import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from ema_scanner.models import Candle, IST
from ema_scanner.universe import eligible_stocks
from ema_scanner.history import parse_candles, validate_history, MinuteBook
from ema_scanner.broker import normalize_token, parse_feed, Broker, RateLimiter, SecureStream
import ssl

NOW = datetime(2026,10,5,10,30,tzinfo=IST)


def option(key='NSE_EQ|A', symbol='A', expiry='2026-10-29', **extra):
    return dict(segment='NSE_FO', instrument_type='CE', underlying_type='EQUITY',
                underlying_key=key, underlying_symbol=symbol, expiry=expiry, **extra)


def eq(key='NSE_EQ|A', symbol='A'):
    return dict(segment='NSE_EQ',instrument_type='EQ',instrument_key=key,trading_symbol=symbol,name=symbol)


def minute(t, price=100):
    return Candle(t,price,price+1,price-1,price+.5,10)


def session(day, count=75):
    start=NOW.replace(day=day,hour=9,minute=15)
    return [minute(start+timedelta(minutes=5*i)) for i in range(count)]


class UniverseTest(unittest.TestCase):
    def test_deduplicate_options_exclude_expired_index_futures_unmapped(self):
        data=[eq(),option(),dict(option(),instrument_type='PE'),
              option('NSE_EQ|B','B','2026-10-04'),eq('NSE_EQ|B','B'),
              dict(option('INDEX|N','N'),underlying_type='INDEX'),
              dict(option('NSE_EQ|F','F'),instrument_type='FUT'),
              option('NSE_EQ|M','M')]
        result,reasons=eligible_stocks(data,NOW.date())
        self.assertEqual([i.symbol for i in result],['A'])
        self.assertTrue(any('unresolved' in r for r in reasons))

    def test_expiry_milliseconds_and_same_day(self):
        expiry=int(NOW.timestamp()*1000)
        result,_=eligible_stocks([eq(),dict(option(),expiry=expiry)],NOW.date())
        self.assertEqual(len(result),1)


class HistoryTest(unittest.TestCase):
    def test_parse_sorted_dedup_completed_regular_only(self):
        times=[NOW-timedelta(minutes=5),NOW,NOW-timedelta(minutes=10)]
        rows=[[t.isoformat(),100,101,99,100,1,0] for t in times]
        rows.append(rows[0])
        result=parse_candles(rows,NOW)
        self.assertEqual([c.time for c in result],sorted(times[::2]))

    def test_invalid_ohlc_rejected(self):
        for high in [99,float('nan')]:
            with self.assertRaises(ValueError):
                parse_candles([[(NOW-timedelta(minutes=5)).isoformat(),100,high,99,100,1]],NOW)

    def test_complete_prior_and_today_sessions(self):
        bars=session(1)+session(2)+session(5,15)
        validate_history(bars,NOW)
        with self.assertRaises(ValueError):
            validate_history(bars[:-1],NOW)
        with self.assertRaises(ValueError):
            validate_history(bars[:20]+bars[21:],NOW)

    def test_no_completed_current_bar_at_open(self):
        validate_history(session(1)+session(2),NOW.replace(hour=9,minute=16))

    def test_minute_assembly_gap_and_late_completion(self):
        start=NOW-timedelta(minutes=5)
        book=MinuteBook()
        rows=[minute(start+timedelta(minutes=i),100+i) for i in range(5)]
        complete,gap=book.update(rows[:4],NOW)
        self.assertEqual(complete,[])
        self.assertTrue(gap)
        complete,gap=book.update(rows[4:],NOW)
        self.assertFalse(gap)
        self.assertEqual((complete[0].open,complete[0].close,complete[0].volume),(100,104.5,50))

    def test_revised_minute_is_not_silently_ignored(self):
        start=NOW-timedelta(minutes=5)
        book=MinuteBook()
        book.update([minute(start+timedelta(minutes=i)) for i in range(5)],NOW)
        revised,_=book.update([minute(start,105)],NOW)
        self.assertEqual(len(revised),1)
        self.assertEqual(revised[0].open,105)


class BrokerTest(unittest.TestCase):
    def test_broker_renews_authorized_url_between_connection_attempts(self):
        urls=[]
        class FakeStream:
            def __init__(self,url,*args,**kwargs):self.url=url;self.renew=kwargs.get('renew_url')
            def run(self):
                urls.append(self.url)
                urls.append(self.renew() if self.renew else self.url)
            def disconnect(self):pass
        class InlineThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        b=Broker('test-token')
        b._json=Mock(side_effect=[{'data':{'authorized_redirect_uri':'wss://example.invalid/one'}},
                                 {'data':{'authorized_redirect_uri':'wss://example.invalid/two'}}])
        with patch('ema_scanner.broker.SecureStream',FakeStream),patch('ema_scanner.broker.threading.Thread',InlineThread):
            b.stream(['A'],Mock(),Mock())
        self.assertEqual(urls,['wss://example.invalid/one','wss://example.invalid/two'])
        self.assertEqual(b._json.call_count,2)
        b.disconnect()

    def test_token_prefix_and_no_response_body_leak(self):
        self.assertEqual(normalize_token('  Bearer abc.def.xyz  '),'abc.def.xyz')
        with self.assertRaises(ValueError): normalize_token('abc\nsecret')
        response=Mock(status_code=401)
        response.text='access_token=secret-value'
        b=Broker('secret-value',get=Mock(return_value=response))
        with self.assertRaisesRegex(RuntimeError,'HTTP 401') as e:
            b._json('https://api.upstox.com/v3/test')
        self.assertNotIn('secret-value',str(e.exception))
        b.disconnect()

    def test_full_feed_minute_and_initial_timestamp(self):
        millis=int(NOW.timestamp()*1000)
        msg={'type':'initial_feed','currentTs':str(millis),
             'marketInfo':{'segmentStatus':{'NSE_EQ':'NORMAL_OPEN'}},
             'feeds':{'NSE_EQ|A':{'fullFeed':{'marketFF':{'ltpc':{'ltp':100,'ltt':millis},
                'marketOHLC':{'ohlc':[{'interval':'I1','ts':millis-60000,'open':100,'high':101,'low':99,'close':100,'vol':5}]}}}}}}
        quotes,minutes,status=parse_feed(msg)
        self.assertEqual(status,'NORMAL_OPEN')
        self.assertTrue(quotes[0].initial)
        self.assertEqual(quotes[0].time,NOW)
        self.assertEqual(len(minutes['NSE_EQ|A']),1)

    def test_rate_limiter_shared_spacing(self):
        clock=Mock(side_effect=[0,0,.25,.25])
        sleeper=Mock()
        rate=RateLimiter(.25,clock,sleeper)
        rate.wait();rate.wait()
        sleeper.assert_called_once_with(.25)

    def test_stream_tls_and_stop_before_open(self):
        transport=Mock()
        stream=SecureStream('wss://example.invalid/feed', ['NSE_EQ|A'], Mock(), Mock(), factory=Mock(return_value=transport))
        stream.run_once()
        self.assertEqual(transport.run_forever.call_args.kwargs['sslopt']['cert_reqs'],ssl.CERT_REQUIRED)
        self.assertTrue(transport.run_forever.call_args.kwargs['sslopt']['check_hostname'])
        stream.disconnect()
        stream.on_open(transport)
        transport.send.assert_not_called()


if __name__=='__main__': unittest.main()

"""The index boundary must never subscribe to shares outside Nifty 50."""
import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch

import requests

from ema_scanner.broker import Broker, MASTER_URL
from ema_scanner.models import IST, Settings
from ema_scanner.storage import data_directory, InstanceLock, SettingsStore

NIFTY50_URL = 'https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv'
TODAY = date(2026, 10, 7)


def csv_text(rows=None):
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(['Company Name', 'Industry', 'Symbol', 'Series', 'ISIN Code'])
    if rows is None:
        rows = [[f'Company {i}, India', 'Industry', f'STOCK{i:02}', 'EQ', f'INE{i:09}']
                for i in range(50)]
    writer.writerows(rows)
    return text.getvalue()


def market_master():
    master = []
    for i in range(51):
        isin = f'INE{i:09}'
        key = 'NSE_EQ|' + isin
        # Symbol 0 has changed name in the broker master. Membership is by ISIN.
        symbol = 'OLDNAME' if i == 0 else f'STOCK{i:02}'
        master.append(dict(segment='NSE_EQ', instrument_type='EQ', instrument_key=key,
                           trading_symbol=symbol, name=f'Company {i}', isin=isin))
        for kind in ('CE', 'PE'):
            master.append(dict(segment='NSE_FO', instrument_type=kind,
                               underlying_type='EQUITY', underlying_key=key,
                               underlying_symbol=symbol, expiry='2026-10-29'))
    return master


def broker_with(master=None, index_response=None):
    responses = {
        MASTER_URL: Mock(status_code=200, content=gzip.compress(json.dumps(
            master if master is not None else market_master()).encode())),
        NIFTY50_URL: index_response or Mock(status_code=200, content=csv_text().encode()),
    }
    get = Mock(side_effect=lambda url, **kwargs: responses[url])
    return Broker('test-token', get=get), get


class Nifty50Test(unittest.TestCase):
    def setUp(self):
        clock = patch('ema_scanner.broker.datetime')
        clock.start().now.return_value = datetime(2026, 10, 7, 10, 30, tzinfo=IST)
        self.addCleanup(clock.stop)

    def test_broker_loads_only_the_50_members_and_uses_current_index_symbol(self):
        broker, get = broker_with()
        result, reasons = broker.universe()
        self.assertEqual(len(result), 50)
        self.assertEqual({r.symbol for r in result}, {f'STOCK{i:02}' for i in range(50)})
        self.assertEqual(result[0].key, 'NSE_EQ|INE000000000')
        self.assertEqual(reasons, [])
        for call in get.call_args_list:
            if call.args[0] == NIFTY50_URL:
                self.assertNotIn('Authorization', call.kwargs.get('headers', {}))
                self.assertNotIn('test-token', str(call))

    def test_expired_options_are_excluded_and_missing_member_is_reported(self):
        master = market_master()
        for row in master:
            if row.get('underlying_key') == 'NSE_EQ|INE000000001':
                row['expiry'] = '2026-10-06'
        broker, _ = broker_with(master)
        result, reasons = broker.universe()
        self.assertEqual(len(result), 49)
        self.assertNotIn('STOCK01', {r.symbol for r in result})
        self.assertTrue(any('STOCK01' in r and 'option' in r.lower() for r in reasons))

    def test_index_failure_stops_connection_without_using_the_full_stock_universe(self):
        broker, _ = broker_with(index_response=Mock(status_code=403, content=b'blocked'))
        with self.assertRaisesRegex(RuntimeError, 'Nifty 50'):
            broker.universe()

    def test_invalid_index_responses_are_rejected_instead_of_scanning_other_shares(self):
        valid = list(csv.reader(io.StringIO(csv_text())))[1:]
        duplicate = valid[:-1] + [valid[0]]
        non_equity = [r[:] for r in valid]
        non_equity[-1][3] = 'BE'
        invalid_isin = [r[:] for r in valid]
        invalid_isin[-1][4] = 'bad-isin'
        for text in ('<html>Access denied</html>', csv_text(valid[:-1]),
                     csv_text() + '"unterminated quote',
                     csv_text(duplicate), csv_text(non_equity), csv_text(invalid_isin)):
            with self.subTest(text=text[:60]):
                broker, _ = broker_with(index_response=Mock(status_code=200, content=text.encode()))
                with self.assertRaisesRegex(RuntimeError, 'Nifty 50'):
                    broker.universe()

    def test_bom_and_quoted_company_names_are_supported(self):
        broker, _ = broker_with(index_response=Mock(status_code=200,
                                                   content=('\ufeff'+csv_text()).encode()))
        result, _ = broker.universe()
        self.assertEqual(len(result), 50)
        self.assertNotIn('OLDNAME', {r.symbol for r in result})

    def test_index_network_failure_has_a_clear_message_without_response_or_token(self):
        broker, get = broker_with()
        responses = get.side_effect
        def failing_get(url, **kwargs):
            if url == NIFTY50_URL:
                raise requests.ConnectionError('private diagnostic test-token')
            return responses(url, **kwargs)
        get.side_effect = failing_get
        with self.assertRaisesRegex(RuntimeError, 'Nifty 50') as raised:
            broker.universe()
        self.assertNotIn('private diagnostic', str(raised.exception))
        self.assertNotIn('test-token', str(raised.exception))

    def test_installation_data_is_separate_from_trend_chase_v1(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'LOCALAPPDATA': temp}):
            self.assertEqual(data_directory(), Path(temp)/'Trend_Chaser_Nifty_50'/'data')

    def test_original_and_nifty50_can_run_with_independent_settings_and_locks(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'LOCALAPPDATA': temp}):
            original = Path(temp)/'Trend_Chase_V1'/'data'
            store = SettingsStore(original/'settings.json')
            store.save(Settings(proximity_pct=.2))
            before = store.path.read_bytes()
            variant = SettingsStore(data_directory()/'settings.json')
            self.assertEqual(variant.load(), Settings())
            variant.save(Settings(proximity_pct=.3))
            self.assertEqual(store.path.read_bytes(), before)
            locks = [InstanceLock(original/'instance.lock'),
                     InstanceLock(data_directory()/'instance.lock'),
                     InstanceLock(data_directory()/'instance.lock')]
            try:
                self.assertTrue(locks[0].acquire())
                self.assertTrue(locks[1].acquire())
                self.assertFalse(locks[2].acquire())
            finally:
                for lock in locks:
                    lock.release()

    def test_symbol_reuse_cannot_include_a_different_company(self):
        master = market_master()
        # The outside stock adopts a member's symbol but keeps its own ISIN.
        for row in master:
            if row.get('instrument_key') == 'NSE_EQ|INE000000050':
                row['trading_symbol'] = 'STOCK00'
            if row.get('underlying_key') == 'NSE_EQ|INE000000050':
                row['underlying_symbol'] = 'STOCK00'
        broker, _ = broker_with(master)
        result, _ = broker.universe()
        self.assertEqual(len(result), 50)
        self.assertNotIn('NSE_EQ|INE000000050', {r.key for r in result})

    def test_key_isin_resolves_members_when_the_optional_isin_field_is_absent(self):
        master = market_master()
        for row in master:
            row.pop('isin', None)
        broker, _ = broker_with(master)
        result, _ = broker.universe()
        self.assertEqual(len(result), 50)

    def test_missing_options_for_all_members_never_falls_back_to_other_stocks(self):
        master = [row for row in market_master()
                  if row.get('segment') == 'NSE_EQ'
                  or row.get('underlying_key') == 'NSE_EQ|INE000000050']
        broker, _ = broker_with(master)
        with self.assertRaisesRegex(RuntimeError, 'Nifty 50 stock-option'):
            broker.universe()


if __name__ == '__main__':
    unittest.main()

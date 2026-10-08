"""Browser-downloaded index lists must preserve the exact index boundary."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ema_scanner import index_universe
from ema_scanner.models import IST
from tests.test_nifty50 import broker_with, csv_text, NIFTY50_URL

NOW = datetime(2026, 10, 8, 10, 30, tzinfo=IST)


class CsvImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def store(self):
        self.assertTrue(hasattr(index_universe, 'ConstituentStore'),
                        'Validated browser CSV storage is missing')
        return index_universe.ConstituentStore(self.root/'data'/'nifty50-constituents.json')

    def source(self, name='ind_nifty50list.csv', text=None):
        path = self.root/name
        path.write_text(csv_text() if text is None else text, encoding='utf-8-sig')
        return path

    def test_import_roundtrip_keeps_validated_members_and_import_time(self):
        store = self.store()
        record = store.import_file(self.source(), now=NOW)
        loaded = self.store().load()
        self.assertEqual(loaded.members, record.members)
        self.assertEqual(len(loaded.members), 50)
        self.assertEqual(loaded.imported_at, NOW)
        self.assertTrue(loaded.current(NOW))
        self.assertFalse(loaded.current(NOW+timedelta(days=1)))
        self.assertFalse(loaded.current(NOW-timedelta(days=1)))

    def test_other_index_filenames_are_rejected_even_when_the_csv_has_50_members(self):
        store = self.store()
        for name in ('ind_niftymidcap50list.csv', 'ind_niftynext50list.csv'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Nifty 50'):
                store.import_file(self.source(name), now=NOW)
        self.assertFalse(store.path.exists())

    def test_browser_duplicate_filename_is_supported(self):
        record = self.store().import_file(self.source('ind_nifty50list (1).csv'), now=NOW)
        self.assertEqual(len(record.members), 50)

    def test_invalid_replacement_preserves_the_previous_import(self):
        store = self.store()
        store.import_file(self.source(), now=NOW)
        before = store.path.read_bytes()
        for text in ('<html>website page</html>', csv_text().replace('STOCK49', 'STOCK00')):
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                store.import_file(self.source(text=text), now=NOW)
            self.assertEqual(store.path.read_bytes(), before)

    def test_corrupt_or_wrong_index_saved_records_are_rejected(self):
        store = self.store()
        store.import_file(self.source(), now=NOW)
        original = json.loads(store.path.read_text())
        for change in ({'index':'NIFTYNEXT50'}, {'csv':'<html>bad</html>'},
                       {'imported_at':'no timestamp'}, {'imported_at':'2026-10-08T10:30:00'}):
            store.path.write_text(json.dumps(original | change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                store.load()

    def test_oversized_csv_is_rejected_without_creating_saved_data(self):
        store = self.store()
        with self.assertRaises(ValueError):
            store.import_file(self.source(text='x'*300_000), now=NOW)
        self.assertFalse(store.path.exists())

    def test_clear_removes_only_the_import_and_is_repeatable(self):
        store = self.store()
        store.import_file(self.source(), now=NOW)
        settings = store.path.parent/'settings.json'
        settings.write_text('preserve me')
        store.clear(); store.clear()
        self.assertIsNone(store.load())
        self.assertEqual(settings.read_text(), 'preserve me')

    def test_current_import_bypasses_the_html_response_and_keeps_index_membership(self):
        store = self.store()
        store.import_file(self.source(), now=NOW)
        broker, _ = broker_with(index_response=Mock(status_code=200, content=b'<html>webpage</html>'))
        broker.constituent_store = store
        with patch('ema_scanner.broker.datetime') as clock:
            clock.now.return_value = NOW
            stocks, reasons = broker.universe()
        self.assertEqual(len(stocks), 50)
        self.assertNotIn('STOCK50', {s.symbol for s in stocks})
        self.assertTrue(any('imported' in r.lower() and '2026-10-08' in r for r in reasons))

    def test_yesterdays_import_cannot_bypass_a_failed_fresh_download(self):
        store = self.store()
        store.import_file(self.source(), now=NOW-timedelta(days=1))
        broker, _ = broker_with(index_response=Mock(status_code=200, content=b'<html>webpage</html>'))
        broker.constituent_store = store
        with patch('ema_scanner.broker.datetime') as clock:
            clock.now.return_value = NOW
            with self.assertRaisesRegex(RuntimeError, 'Load official CSV'):
                broker.universe()

    def test_html_response_has_actionable_error_without_exposing_body_or_token(self):
        broker, _ = broker_with(index_response=Mock(
            status_code=200, content=b'<html>private-response test-token</html>'))
        with self.assertRaises(RuntimeError) as raised:
            broker.universe()
        message = str(raised.exception)
        self.assertIn('webpage', message)
        self.assertIn('Load official CSV', message)
        self.assertNotIn('private-response', message)
        self.assertNotIn('test-token', message)

    def test_http_error_preserves_status_and_explains_browser_import(self):
        broker, _ = broker_with(index_response=Mock(status_code=403, content=b'private-response'))
        with self.assertRaises(RuntimeError) as raised:
            broker.universe()
        self.assertIn('HTTP 403', str(raised.exception))
        self.assertIn('Load official CSV', str(raised.exception))

    def test_invalid_utf8_download_is_rejected_even_when_membership_columns_look_valid(self):
        raw=csv_text().encode().replace(b'Company 0', b'\xffCompany 0', 1)
        broker, _=broker_with(index_response=Mock(status_code=200,content=raw))
        with self.assertRaisesRegex(RuntimeError, 'invalid CSV'):
            broker.universe()


if __name__ == '__main__':
    unittest.main()

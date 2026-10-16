import unittest
from global_trend.catalog import default_catalog, resolve_catalog


class CatalogTest(unittest.TestCase):
    def test_only_evidenced_common_matches_are_enabled(self):
        rows = default_catalog()
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(r.verified for r in rows), 9)
        self.assertEqual(sum(r.group == 'Forex' for r in rows), 10)
        self.assertFalse(next(r for r in rows if r.key == 'NASDAQ').verified)
        self.assertEqual(len({r.key for r in rows}), len(rows))

    def test_names_resolve_without_hardcoded_ids(self):
        apple = next(r for r in default_catalog() if r.key == 'AAPL')
        resolved, reasons = resolve_catalog([apple], [
            {'symbolId': 934, 'symbolName': 'APPLE', 'enabled': True}])
        self.assertEqual(resolved[0].symbol_id, 934)
        self.assertEqual(resolved[0].entry.olymp_name, 'Apple')
        self.assertEqual(reasons, {})

    def test_ambiguous_disabled_and_missing_symbols_do_not_substitute(self):
        apple = next(r for r in default_catalog() if r.key == 'AAPL')
        for symbols in [[], [{'symbolId':1,'symbolName':'APPLE','enabled':False}],
                        [{'symbolId':1,'symbolName':'APPLE'}, {'symbolId':2,'symbolName':'Apple'}]]:
            resolved, reasons = resolve_catalog([apple], symbols)
            self.assertEqual(resolved, [])
            self.assertIn(apple.key, reasons)


if __name__ == '__main__': unittest.main()

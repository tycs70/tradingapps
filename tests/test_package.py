import json
from pathlib import Path
import tempfile
import unittest

from tools.build_release import safe_relative, manifest_for, verify_tree, build_lock, validate_wheels


class PackageTest(unittest.TestCase):
    def test_windows_and_posix_escape_paths_rejected(self):
        for value in ['../x','/tmp/x','C:/x','a/../../x','a\\b','a//b']:
            with self.assertRaises(ValueError):safe_relative(value)
        self.assertEqual(safe_relative('app/ema_scanner/ui.py'),'app/ema_scanner/ui.py')

    def test_manifest_detects_corruption_missing_and_unexpected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'app').mkdir();file=root/'app'/'x.py';file.write_text('original')
            (root/'manifest.json').write_text(json.dumps(manifest_for(root)))
            verify_tree(root)
            file.write_text('changed')
            with self.assertRaisesRegex(ValueError,'hash'):verify_tree(root)
            file.write_text('original');(root/'extra.py').write_text('injected')
            with self.assertRaisesRegex(ValueError,'unexpected'):verify_tree(root)
            (root/'extra.py').unlink();file.unlink()
            with self.assertRaisesRegex(ValueError,'missing'):verify_tree(root)

    def test_manifest_path_attack_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'manifest.json').write_text(json.dumps({'files':{'../secret':'0'*64}}))
            with self.assertRaises(ValueError):verify_tree(root)

    def test_windows_wheel_set_complete_and_locked(self):
        root=Path(__file__).resolve().parents[1]/'build'/'wheels'
        if not root.exists():self.skipTest('Release wheel cache unavailable')
        records=validate_wheels(root)
        self.assertEqual(len(records),12)
        lock=build_lock(records)
        self.assertEqual(lock.count('--hash=sha256:'),12)
        self.assertIn('upstox-python-sdk==2.23.0',lock)
        self.assertFalse(any('manylinux' in r['file'] for r in records))


if __name__=='__main__':unittest.main()

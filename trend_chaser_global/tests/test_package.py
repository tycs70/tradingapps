import json,hashlib,zipfile,tempfile,unittest
from pathlib import Path
from tools.build_release import safe_relative,manifest_for,verify_tree,validate_wheels,build_lock,verify_reference

ROOT=Path(__file__).resolve().parents[1]
class PackageTest(unittest.TestCase):
    def test_escape_paths_and_symlinks_rejected(self):
        for p in ('../x','/tmp/x','C:/x','a/../../x','a\\b','a//b','a. /b','CON.txt','a/x:ads'):
            with self.assertRaises(ValueError):safe_relative(p)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'link').symlink_to('/etc/hostname')
            with self.assertRaises(ValueError):manifest_for(root)
    def test_manifest_rejects_corruption_missing_extra_and_path_attack(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);f=root/'x.py';f.write_text('original')
            manifest=manifest_for(root);(root/'manifest.json').write_text(json.dumps(manifest));verify_tree(root)
            f.write_text('changed')
            with self.assertRaisesRegex(ValueError,'hash'):verify_tree(root)
            f.write_text('original');(root/'extra').write_text('x')
            with self.assertRaisesRegex(ValueError,'unexpected'):verify_tree(root)
            (root/'extra').unlink();f.unlink()
            with self.assertRaisesRegex(ValueError,'missing'):verify_tree(root)
            (root/'manifest.json').write_text(json.dumps({'files':{'../escape':'0'*64}}))
            with self.assertRaises(ValueError):verify_tree(root)
    def test_reference_manifest_must_match_before_runtime_is_reused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('reference/runtime.zip',b'not runtime')
                z.writestr('reference/manifest.json',json.dumps({'files':{'runtime.zip':'0'*64}}))
            with self.assertRaises(ValueError):verify_reference(p)
    def test_windows_wheels_are_complete_and_trusted(self):
        wheel_dir=ROOT/'build/wheels'
        if not wheel_dir.exists():self.skipTest('Windows wheel cache not built yet')
        records=validate_wheels(wheel_dir)
        self.assertEqual(len(records),7)
        self.assertEqual(build_lock(records).count('--hash=sha256:'),7)
        self.assertFalse(any('upstox' in r['name'] for r in records))
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            for f in wheel_dir.glob('*.whl'):(p/f.name).write_bytes(f.read_bytes())
            wheel=next(p.glob('*.whl'));data=bytearray(wheel.read_bytes());data[-1]^=1;wheel.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'trusted|hash'):validate_wheels(p)
    def test_independent_installer_uses_offline_hashes_and_own_lock(self):
        install=(ROOT/'installer/install.ps1').read_text();uninstall=(ROOT/'installer/uninstall.ps1').read_text()
        self.assertIn('--require-hashes',install);self.assertIn('--no-index',install)
        self.assertIn('global.lock',install);self.assertIn('global.lock',uninstall)
        self.assertIn('assets\\icon.ico',install);self.assertIn('Trend_Chaser_Global',uninstall)
        self.assertNotIn('EMA_PreCross_Scanner',install+uninstall)
        self.assertNotIn('Remove-Item -LiteralPath $Data',install)

if __name__=='__main__':unittest.main()

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil
import zipfile
import os
import struct
import sys

from tools.build_release import safe_relative, manifest_for, verify_tree, build_lock, validate_wheels
from tools import build_release

ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def build_sample(self, root):
        # Only the expensive authenticated runtime conversion is replaced; all
        # source copying, manifest generation, wheel locks and ZIP paths are real.
        for folder in ('ema_scanner', 'tests', 'tools', 'installer'):
            shutil.copytree(ROOT/folder, root/folder, ignore=shutil.ignore_patterns('__pycache__'))
        for folder in ('docs', 'assets'):
            if (ROOT/folder).exists():shutil.copytree(ROOT/folder, root/folder)
            else:(root/folder).mkdir()
        for name in ('run_app.pyw','verify_install.py','requirements.txt','requirements.lock.txt',
                     'README.md','README_FIRST.txt','demo.html','demo.png'):
            if (ROOT/name).exists():shutil.copy2(ROOT/name, root/name)
            else:(root/name).write_text('test fixture')
        shutil.copytree(ROOT/'build'/'wheels',root/'build'/'wheels')
        with patch.object(build_release,'ROOT',root), patch.object(
                build_release,'runtime_zip',side_effect=lambda archive,output: output.write_bytes(b'test runtime')):
            return build_release.build(root/'unused.tar.gz')

    def test_release_has_independent_identity_and_complete_preview_assets(self):
        if not (ROOT/'build'/'wheels').exists():
            self.skipTest('Developer release wheel cache unavailable; installed app does not retain it')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=self.build_sample(root)
            self.assertEqual(output.name,'Trend_Chaser_Nifty_Next_50_1.0.0_Windows_x64.zip')
            folder=root/'build'/'release'/'Trend_Chaser_Nifty_Next_50_1.0.0'
            verify_tree(folder)
            required={'app/assets/trend-chase.ico','app/assets/trend-chase.png','app/ema_scanner/trends.py',
                      'app/ema_scanner/index_universe.py',
                      'app/ema_scanner/demo.py','app/verify_install.py','app/demo.html','app/demo.png',
                      'app/docs/VALIDATION.md','app/README.md','README_FIRST.txt','demo.html','demo.png',
                      'install.ps1','uninstall.ps1','common.ps1','INSTALL.bat','runtime.zip',
                      'requirements-windows.lock.txt'}
            manifest=json.loads((folder/'manifest.json').read_text())
            self.assertTrue(required<=set(manifest['files']),required-set(manifest['files']))
            self.assertEqual(manifest['version'],'1.0.0')
            self.assertEqual(manifest['runtime_source_sha256'],build_release.RUNTIME_HASH)
            with zipfile.ZipFile(output) as package:
                self.assertTrue(all(name.startswith('Trend_Chaser_Nifty_Next_50_1.0.0/') for name in package.namelist()))
                self.assertEqual(package.read('Trend_Chaser_Nifty_Next_50_1.0.0/demo.html'),(ROOT/'demo.html').read_bytes())
            self.assertEqual(output.with_suffix('.zip.sha256').read_text().split()[0],build_release.digest(output))

    def test_installer_targets_only_its_owned_app_and_creates_offline_demo(self):
        install=(ROOT/'installer/install.ps1').read_text()
        uninstall=(ROOT/'installer/uninstall.ps1').read_text()
        common=(ROOT/'installer/common.ps1').read_text()
        for text in (install,uninstall,common):
            self.assertNotIn('EMA_PreCross_Scanner',text)
            self.assertNotIn('EMA Pre-Cross Scanner',text)
            self.assertNotIn('Trend_Chase_V1',text)
            self.assertNotIn('.trend-chase-v1-owned',text)
            self.assertNotIn('Trend_Chaser_Nifty_50',text)
            self.assertNotIn('.trend-chaser-nifty50-owned',text)
            self.assertIn('.trend-chaser-niftynext50-owned',text)
        for text in (install,uninstall):
            self.assertIn("'Trend_Chaser_Nifty_Next_50'",text)
            self.assertIn('Uninstall\\Trend_Chaser_Nifty_Next_50',text)
            self.assertIn('Trend Chaser Nifty Next 50.lnk',text)
        self.assertIn("DisplayVersion -Value '1.0.0'",install)
        self.assertIn('app\\assets\\trend-chase.ico',install)
        self.assertIn('Trend Chaser Nifty Next 50 Demo.lnk',install)
        self.assertIn('--demo',install)
        self.assertIn('--require-hashes',install)
        self.assertIn('--no-index',install)
        self.assertIn('Assert-OwnedRoot $Root',install)
        self.assertIn('if ($RemoveData)',uninstall)
        self.assertIn('Get-Content -LiteralPath $Marker -Raw',uninstall)

    def test_icon_is_real_multisize_windows_icon(self):
        icon=ROOT/'assets/trend-chase.ico'
        self.assertTrue(icon.is_file(),'Custom Windows app icon missing')
        value=icon.read_bytes();reserved,kind,count=struct.unpack('<HHH',value[:6])
        self.assertEqual((reserved,kind),(0,1));self.assertGreaterEqual(count,3)
        sizes=set()
        for i in range(count):
            width,height,_,_,planes,bits,size,offset=struct.unpack('<BBBBHHII',value[6+16*i:22+16*i])
            sizes.add(width or 256)
            self.assertEqual(width,height);self.assertGreater(size,0)
            self.assertLessEqual(offset+size,len(value))
        self.assertTrue({16,32,256}<=sizes)

    def test_runtime_mismatch_rejected_before_unpacking(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'bad.tar.gz';archive.write_bytes(b'untrusted')
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                build_release.runtime_zip(archive,root/'runtime.zip')
            self.assertFalse((root/'runtime.zip').exists())

    def test_offline_verifier_exercises_trends_demo_and_native_security_boundary(self):
        from verify_install import verify
        report=verify(no_display=True)
        self.assertIsInstance(report,dict)
        self.assertEqual(report['trend_lifecycle'],'passed')
        self.assertEqual(report['offline_demo'],'passed')
        self.assertEqual(report.get('niftynext50_universe'),'passed')
        self.assertEqual(report['dpapi'],'passed' if os.name=='nt' else 'unavailable on this platform; no plaintext fallback')

    def test_verifier_initializes_private_runtime_tcl_paths(self):
        from verify_install import verify
        with tempfile.TemporaryDirectory() as temp:
            runtime=Path(temp)
            for name in ('tcl8.6','tk8.6'):(runtime/'tcl'/name).mkdir(parents=True)
            with patch.object(sys,'executable',str(runtime/'python.exe')), patch.dict(
                    os.environ,{'TCL_LIBRARY':'outside-runtime','TK_LIBRARY':'outside-runtime'}):
                verify(no_display=True)
                self.assertEqual(os.environ['TCL_LIBRARY'],str(runtime/'tcl/tcl8.6'))
                self.assertEqual(os.environ['TK_LIBRARY'],str(runtime/'tcl/tk8.6'))

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

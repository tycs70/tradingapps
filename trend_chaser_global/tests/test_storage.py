from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from global_trend.credentials import CredentialStore
from global_trend.models import Settings
from global_trend.storage import SettingsStore
from tests.test_credentials import FakeCipher


class CredentialTest(unittest.TestCase):
    def test_credentials_roundtrip_is_protected_and_forget_clears(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'credentials.dpapi';store=CredentialStore(path,cipher=FakeCipher())
            self.assertTrue(store.save({'client_id':'id','client_secret':'SECRET','refresh_token':'REFRESH'},remember=True))
            self.assertNotIn(b'SECRET',path.read_bytes());self.assertNotIn(b'REFRESH',path.read_bytes())
            loaded=CredentialStore(path,cipher=FakeCipher()).load()
            self.assertEqual(loaded['refresh_token'],'REFRESH')
            store.clear();self.assertFalse(path.exists());self.assertIsNone(store.load())

    def test_refresh_save_failure_retains_memory_credentials(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'credentials.dpapi';store=CredentialStore(path,cipher=FakeCipher())
            store.save({'refresh_token':'old'},remember=True)
            with patch.object(store.cipher,'protect',side_effect=OSError('LEAKSECRET')):
                self.assertFalse(store.save({'refresh_token':'rotated'},remember=True))
            self.assertEqual(store.load()['refresh_token'],'rotated')
            self.assertNotIn('LEAKSECRET',store.warning)
            self.assertNotIn(b'rotated',path.read_bytes())

    def test_non_windows_memory_only_retains_no_file(self):
        with tempfile.TemporaryDirectory() as t:
            store=CredentialStore(Path(t)/'credentials.dpapi')
            store.save({'access_token':'SECRET'},remember=False)
            self.assertEqual(store.load()['access_token'],'SECRET')
            self.assertFalse(store.path.exists())


class PreferenceTest(unittest.TestCase):
    def test_global_boundary_roundtrip_excludes_unknown_secret_fields(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'settings.json';store=SettingsStore(path)
            store.save(Settings(day_boundary='18:00',day_zone='America/New_York'))
            data=json.loads(path.read_text());data['access_token']='UNWANTED';path.write_text(json.dumps(data))
            loaded=store.load();self.assertEqual(loaded.day_boundary,'18:00')
            store.save(loaded);self.assertNotIn('UNWANTED',path.read_text())

    def test_invalid_boundary_and_zone_rejected(self):
        for kwargs in [{'day_boundary':'29:00'},{'day_zone':'not/a-zone'},
                       {'day_boundary':None},{'day_boundary':123}]:
            with self.assertRaises(ValueError):Settings(**kwargs)


if __name__=='__main__':unittest.main()

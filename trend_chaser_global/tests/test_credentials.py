"""Persistence behavior; native protection is additionally exercised on Windows."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class FakeCipher:
    """Reversible test-only adapter for the unavailable native Windows boundary."""
    available=True

    def protect(self,value):
        return b'test-only\x00'+bytes(byte^0xA5 for byte in value)

    def unprotect(self,value):
        if not value.startswith(b'test-only\x00'):raise OSError('Cannot decrypt')
        return bytes(byte^0xA5 for byte in value[10:])


class TokenStorageTest(unittest.TestCase):
    def setUp(self):
        from global_trend.credentials import TokenStore
        self.temp=tempfile.TemporaryDirectory()
        self.store=TokenStore(Path(self.temp.name)/'data'/'upstox-token.dpapi',cipher=FakeCipher())

    def tearDown(self):self.temp.cleanup()

    def test_token_roundtrip_writes_only_protected_bytes(self):
        self.assertIsNone(self.store.load())
        self.store.save('private-token')
        self.assertNotIn(b'private-token',self.store.path.read_bytes())
        self.assertEqual(self.store.load(),'private-token')
        self.assertEqual(list(self.store.path.parent.iterdir()),[self.store.path])

    def test_protection_failure_preserves_previous_blob(self):
        self.store.save('previous-token');previous=self.store.path.read_bytes()
        with patch.object(self.store.cipher,'protect',side_effect=OSError('Protection failed')):
            with self.assertRaises(OSError):self.store.save('new-private-token')
        self.assertEqual(self.store.path.read_bytes(),previous)
        self.assertNotIn(b'new-private-token',previous)

    def test_failed_atomic_write_preserves_blob_and_removes_temporary_file(self):
        self.store.save('previous-token');previous=self.store.path.read_bytes()
        with patch('global_trend.credentials.os.replace',side_effect=OSError('Cannot replace')):
            with self.assertRaises(OSError):self.store.save('new-private-token')
        self.assertEqual(self.store.path.read_bytes(),previous)
        self.assertEqual(list(self.store.path.parent.iterdir()),[self.store.path])

    def test_corrupt_or_plaintext_token_is_rejected(self):
        self.store.path.parent.mkdir()
        self.store.path.write_bytes(b'private-token')
        with self.assertRaises(OSError):self.store.load()
        self.store.save('private-token')
        with patch.object(self.store.cipher,'unprotect',side_effect=OSError('Cannot decrypt')):
            with self.assertRaises(OSError):self.store.load()

    def test_forget_is_idempotent(self):
        self.store.clear();self.store.save('private-token');self.store.clear();self.store.clear()
        self.assertFalse(self.store.path.exists())
        self.assertIsNone(self.store.load())

    @unittest.skipIf(os.name=='nt','Non-Windows behavior')
    def test_non_windows_refuses_plaintext_fallback(self):
        from global_trend.credentials import WindowsDPAPI, TokenStore
        cipher=WindowsDPAPI()
        self.assertFalse(cipher.available)
        store=TokenStore(self.store.path,cipher=cipher)
        with self.assertRaises(OSError):store.save('private-token')
        self.assertFalse(store.path.exists())

    @unittest.skipUnless(os.name=='nt','Requires native Windows DPAPI')
    def test_native_windows_roundtrip_and_tamper_rejection(self):
        from global_trend.credentials import WindowsDPAPI
        cipher=WindowsDPAPI();secret=b'offline-self-check-only'
        protected=cipher.protect(secret)
        self.assertNotIn(secret,protected)
        self.assertEqual(cipher.unprotect(protected),secret)
        with self.assertRaises(OSError):cipher.unprotect(b'invalid-protected-data')


if __name__=='__main__':unittest.main()

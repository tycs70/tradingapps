from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile,time,threading,unittest
from global_trend.connection import ConnectionController,MappingStore
from global_trend.auth import TokenBundle
from global_trend.credentials import CredentialStore
from global_trend.catalog import CatalogEntry,default_catalog

class Engine:
    def __init__(self):self.clients=[];self.entries=default_catalog()
    def connect(self,c):self.clients.append(c)
    def disconnect(self):pass

class Client:
    gate=None
    def __init__(self,*args):self.closed=False;self.account_id=None
    def accounts(self,t):
        return [{'account_id':123,'login':5923508,'is_live':False,'broker':'Spotware'},
                {'account_id':456,'login':22,'is_live':True,'broker':'Live'}]
    def authorize(self,a,t):
        if self.gate:self.gate.wait(2)
        self.account_id=a
    def close(self):self.closed=True

class ConnectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=Engine()
        self.c=ConnectionController(self.engine,CredentialStore(Path(self.tmp.name)/'secret'),client_factory=Client)
        self.c.configure('id','secret','http://localhost/')
        self.c.tokens=TokenBundle('access','refresh',datetime.now(timezone.utc)+timedelta(hours=1))
    def tearDown(self):self.c.close();Client.gate=None;self.tmp.cleanup()
    def wait(self):
        end=time.monotonic()+3
        while self.c.busy and time.monotonic()<end:self.c.poll();time.sleep(.01)
        self.c.poll();self.assertFalse(self.c.busy)
    def test_demo_selection_uses_internal_id_and_rejects_live(self):
        self.c.load_accounts();self.wait();self.assertEqual(len(self.c.accounts),1)
        with self.assertRaises(ValueError):self.c.connect(456)
        self.c.connect(123);self.wait();self.assertEqual(self.engine.clients[0].account_id,123)
    def test_disconnect_cancels_late_authorization(self):
        self.c.load_accounts();self.wait();Client.gate=threading.Event()
        self.c.connect(123);self.c.disconnect();Client.gate.set();self.wait()
        self.assertFalse(self.engine.clients)
    def test_errors_never_echo_secret_exception_text(self):
        class Bad(Client):
            def accounts(self,t):raise RuntimeError('SECRET_VALUE ACCESS_VALUE REFRESH_VALUE')
        self.c.client_factory=Bad;self.c.load_accounts();self.wait()
        for private in ('SECRET_VALUE','ACCESS_VALUE','REFRESH_VALUE'):self.assertNotIn(private,self.c.message)
    def test_mapping_is_account_scoped_and_renaming_revokes_confirmation(self):
        store=MappingStore(Path(self.tmp.name)/'mapping.json')
        entry=CatalogEntry('NEW','Shares','New share','BROKER',True)
        store.save(123,[entry]);self.assertEqual(store.load(123),(entry,))
        self.assertEqual(store.load(456),default_catalog())
        changed=store.edit(entry,ctrader_name='OTHER',verified=True)
        self.assertFalse(changed.verified)
        with self.assertRaises(ValueError):store.save(123,[entry,entry])

    def test_refresh_rotates_saved_token_and_reconnects_selected_demo(self):
        class OAuth:
            def refresh(self,t):return TokenBundle('ROTATED_ACCESS','ROTATED_REFRESH',datetime.now(timezone.utc)+timedelta(hours=1))
        self.c.oauth=OAuth();self.c.load_accounts();self.wait()
        self.c.connect(123);self.wait()
        self.c.tokens=TokenBundle('old','old_refresh',datetime.now(timezone.utc))
        self.c.poll();self.wait();self.wait()
        self.assertEqual(self.c.tokens.refresh_token,'ROTATED_REFRESH')
        self.assertEqual(self.c.credentials.load()['refresh_token'],'ROTATED_REFRESH')
        self.assertEqual(len(self.engine.clients),2)

if __name__=='__main__':unittest.main()

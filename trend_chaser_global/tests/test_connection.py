from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile,time,threading,unittest
from global_trend.connection import ConnectionController,MappingStore
from global_trend.auth import TokenBundle
from global_trend.credentials import CredentialStore
from global_trend.catalog import CatalogEntry,default_catalog

class Engine:
    def __init__(self):self.clients=[];self.entries=default_catalog();self.connection_state='idle';self.connection_retry_after=0
    def connect(self,c):self.clients.append(c);self.connection_state='connected'
    def disconnect(self):self.connection_state='idle'
    def interrupt(self):self.connection_state='interrupted';self.clients[-1].close()

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

    def connected_with_clock(self):
        self.clock=[0.0];self.c._clock=lambda:self.clock[0]
        self.c.load_accounts();self.wait();self.c.connect(123);self.wait()

    def test_interrupted_connection_reauthorizes_same_demo_without_browser(self):
        self.connected_with_clock();old=self.engine.clients[-1]
        self.engine.interrupt();self.c.poll()
        self.clock[0]=2.1;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),2)
        self.assertEqual(self.engine.clients[-1].account_id,123)
        self.assertIsNot(old,self.engine.clients[-1]);self.assertTrue(old.closed)

    def test_repeated_failed_reconnections_back_off(self):
        from global_trend.transport import TransportError
        self.connected_with_clock();attempts=[]
        class Flaky(Client):
            def authorize(self,account,tokens):
                attempts.append(account)
                if len(attempts)<3:raise TransportError('PRIVATE_NETWORK_DETAIL')
                super().authorize(account,tokens)
        self.c.client_factory=Flaky;self.engine.interrupt();self.c.poll()
        for current,expected in ((2.1,1),(5,1),(6.2,2),(13,2),(14.3,3)):
            self.clock[0]=current;self.c.poll();self.wait()
            self.assertEqual(len(attempts),expected)
            self.assertNotIn('PRIVATE_NETWORK_DETAIL',self.c.message)
        self.assertEqual(len(self.engine.clients),2)

    def test_manual_disconnect_cancels_scheduled_recovery(self):
        self.connected_with_clock();self.engine.interrupt();self.c.poll()
        self.c.disconnect();self.clock[0]=100;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),1)

    def test_manual_disconnect_cancels_recovery_in_flight(self):
        self.connected_with_clock();self.engine.interrupt();self.c.poll()
        Client.gate=threading.Event();self.clock[0]=2.1;self.c.poll()
        self.c.disconnect();Client.gate.set();self.wait()
        self.clock[0]=100;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),1)

    def test_refresh_after_manual_disconnect_does_not_resume_stream(self):
        class OAuth:
            def refresh(self,t):return TokenBundle('NEW_ACCESS','NEW_REFRESH',datetime.now(timezone.utc)+timedelta(hours=1))
        self.connected_with_clock();self.c.oauth=OAuth();self.c.disconnect()
        self.c.tokens=TokenBundle('old','old_refresh',datetime.now(timezone.utc))
        self.c.poll();self.wait();self.wait()
        self.assertEqual(len(self.engine.clients),1)
        self.assertEqual(self.c.tokens.refresh_token,'NEW_REFRESH')

    def test_invalid_authorization_stops_automatic_retries(self):
        from global_trend.transport import AuthorizationError
        self.connected_with_clock();attempts=[]
        class Rejected(Client):
            def authorize(self,account,tokens):attempts.append(account);raise AuthorizationError()
        self.c.client_factory=Rejected;self.engine.interrupt();self.c.poll()
        self.clock[0]=2.1;self.c.poll();self.wait()
        self.clock[0]=1000;self.c.poll();self.wait()
        self.assertEqual(attempts,[123]);self.assertIn('authorize again',self.c.message)

    def test_broker_retry_delay_is_preserved_during_recovery(self):
        self.connected_with_clock();self.engine.interrupt();self.engine.connection_retry_after=120
        self.c.poll();self.clock[0]=119;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),1)
        self.clock[0]=121;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),2)

    def test_refresh_respects_broker_cooldown_even_before_first_recovery_poll(self):
        class OAuth:
            def refresh(self,t):return TokenBundle('new','rotated',datetime.now(timezone.utc)+timedelta(hours=1))
        self.connected_with_clock();self.c.oauth=OAuth()
        self.engine.interrupt();self.engine.connection_retry_after=120
        self.c.tokens=TokenBundle('old','old_refresh',datetime.now(timezone.utc))
        self.c.poll();self.wait()
        self.assertEqual(self.c.tokens.refresh_token,'rotated')
        self.assertEqual(len(self.engine.clients),1)
        self.clock[0]=119;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),1)
        self.clock[0]=121;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),2)

    def start_gated_refresh(self):
        gate=threading.Event();started=threading.Event();finished=threading.Event()
        class OAuth:
            def refresh(self,t):
                started.set();gate.wait(2);finished.set()
                return TokenBundle('new','rotated',datetime.now(timezone.utc)+timedelta(hours=1))
        self.c.oauth=OAuth();self.c.tokens=TokenBundle('old','old_refresh',datetime.now(timezone.utc))
        self.c.poll();self.assertTrue(started.wait(1))
        self.addCleanup(gate.set)
        return gate,finished

    def test_disconnect_during_refresh_keeps_rotated_token_without_resuming(self):
        self.connected_with_clock();gate,finished=self.start_gated_refresh()
        self.c.disconnect();gate.set();self.assertTrue(finished.wait(1));self.wait()
        self.assertIsNotNone(self.c.tokens)
        self.assertEqual(self.c.tokens.refresh_token,'rotated')
        self.assertEqual(self.c.credentials.load()['refresh_token'],'rotated')
        self.assertEqual(len(self.engine.clients),1)
        self.c.connect(123);self.wait()
        self.assertEqual(len(self.engine.clients),2)

    def test_own_token_invalidation_during_successful_refresh_resumes_connection(self):
        self.connected_with_clock();gate,finished=self.start_gated_refresh()
        self.engine.connection_state='authorization_required';self.c.poll()
        gate.set();self.assertTrue(finished.wait(1));self.wait();self.wait()
        self.assertIsNotNone(self.c.tokens)
        self.assertEqual(self.c.tokens.refresh_token,'rotated')
        self.assertEqual(len(self.engine.clients),2)

    def test_failed_renewal_after_token_invalidation_requires_authorization(self):
        from global_trend.auth import AuthError
        class OAuth:
            def refresh(self,t):raise AuthError('PRIVATE_DETAIL')
        self.connected_with_clock();self.c.oauth=OAuth()
        self.c.tokens=TokenBundle('old','old_refresh',datetime.now(timezone.utc))
        self.c.poll();self.engine.connection_state='authorization_required';self.wait()
        self.clock[0]=1000;self.c.poll();self.wait()
        self.assertEqual(len(self.engine.clients),1)
        self.assertIn('authorization again',self.c.message)
        self.assertNotIn('PRIVATE_DETAIL',self.c.message)

    def test_forget_during_refresh_discards_rotated_token(self):
        self.connected_with_clock();gate,finished=self.start_gated_refresh()
        self.c.forget();gate.set();self.assertTrue(finished.wait(1));self.wait()
        self.assertIsNone(self.c.tokens);self.assertIsNone(self.c.credentials.load())
        self.assertEqual(len(self.engine.clients),1)

    def test_changed_credentials_discard_late_refresh_result(self):
        self.connected_with_clock();gate,finished=self.start_gated_refresh()
        self.c.configure('different_id','different_secret','http://localhost/')
        gate.set();self.assertTrue(finished.wait(1));self.wait()
        self.assertIsNone(self.c.tokens)
        self.assertEqual(len(self.engine.clients),1)

    def test_recovery_client_creation_failure_does_not_escape_ui_poll(self):
        self.connected_with_clock();attempts=[]
        def unavailable(*args):attempts.append(1);raise RuntimeError('PRIVATE_CONSTRUCTOR_DETAIL')
        self.c.client_factory=unavailable;self.engine.interrupt();self.c.poll()
        self.clock[0]=2.1
        try:self.c.poll()
        except Exception:self.fail('Automatic reconnect construction escaped the UI poll')
        self.assertEqual(len(attempts),1);self.assertFalse(self.c.busy)
        self.assertNotIn('PRIVATE_CONSTRUCTOR_DETAIL',self.c.message)

if __name__=='__main__':unittest.main()

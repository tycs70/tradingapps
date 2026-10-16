"""Background connection workflow. Only poll() publishes results to the UI thread."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict,replace
from datetime import datetime,timezone
import json,os,queue,re,tempfile,threading,time
from pathlib import Path
from .auth import OAuthSession,TokenBundle
from .catalog import CatalogEntry,GROUPS,default_catalog
from .ctrader import CTraderClient
from .auth import AuthError
from .transport import AuthorizationError,RateLimitError


class MappingStore:
    def __init__(self,path):self.path=Path(path)
    @staticmethod
    def validate(entries):
        entries=tuple(entries)
        if len(entries)>500 or len({e.key for e in entries})!=len(entries):
            raise ValueError('Use unique instrument keys and at most 500 rows.')
        for e in entries:
            if (not re.fullmatch(r'[A-Z0-9_]{1,32}',e.key) or e.group not in GROUPS or
                not all(isinstance(v,str) and 0<len(v.strip())<=120 and not any(ord(c)<32 for c in v)
                        for v in (e.olymp_name,e.ctrader_name)) or not isinstance(e.verified,bool)):
                raise ValueError('Enter a key, valid section and both exact instrument names.')
        return entries
    def load(self,account):
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            rows=data.get(str(int(account)))
            return default_catalog() if rows is None else self.validate(CatalogEntry(**r) for r in rows)
        except (OSError,ValueError,TypeError,AttributeError):return default_catalog()
    def save(self,account,entries):
        rows=self.validate(entries)
        try:data=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):data={}
        if not isinstance(data,dict):data={}
        data[str(int(account))]=[asdict(e) for e in rows]
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(dir=self.path.parent,prefix='.mappings-')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,indent=2)
            os.replace(temp,self.path)
        finally:Path(temp).unlink(missing_ok=True)
    @staticmethod
    def edit(entry,**changes):
        updated=replace(entry,**changes)
        if (updated.olymp_name,updated.ctrader_name,updated.group)!=(entry.olymp_name,entry.ctrader_name,entry.group):
            updated=replace(updated,verified=False)
        return updated


class ConnectionController:
    def __init__(self,engine,credentials,mappings=None,client_factory=CTraderClient,oauth_factory=OAuthSession,clock=None):
        self.engine=engine;self.credentials=credentials;self.mappings=mappings
        self.client_factory=client_factory;self.oauth_factory=oauth_factory
        self.tokens=None;self.accounts=();self.account=None;self.config=None;self.oauth=None
        self.remember=False;self.message='Enter your registered cTrader application details.'
        self.busy=False;self.closed=False;self._generation=0;self._active=None
        self._auth_generation=0;self._job_serial=0;self._busy_job=None
        self._renewal_auth=None
        self._pending=set();self._lock=threading.Lock();self._results=queue.Queue()
        self._executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='ctrader-connect')
        self._clock=clock or time.monotonic;self._wanted=False;self._desired_account=None
        self._retry_at=None;self._retry_attempt=0;self._stable_since=None
    def configure(self,client_id,secret,redirect):
        config=(client_id.strip(),secret.strip(),redirect.strip())
        oauth=self.oauth_factory(*config)
        if config!=self.config:
            self.disconnect();self.tokens=None;self.accounts=();self.account=None
            self._auth_generation+=1
        self.config=config;self.oauth=oauth
    def restore(self):
        data=self.credentials.load()
        if not data:return
        try:
            self.configure(data['client_id'],data['client_secret'],data['redirect_uri'])
            self.tokens=TokenBundle.from_dict(data);self.account=data.get('account_id')
            self.remember=True;self.message='Saved authorization restored. Load demo accounts to reconnect.'
        except (KeyError,ValueError,RuntimeError):self.message='Authorize again to restore the connection.'
    def _save(self):
        if not self.tokens or not self.config:return
        data=dict(zip(('client_id','client_secret','redirect_uri'),self.config))
        data.update(self.tokens.to_dict(),account_id=self.account)
        self.credentials.save(data,remember=self.remember)
        if self.credentials.warning:self.message=self.credentials.warning
    def _job(self,kind,work):
        if self.closed:raise ValueError('Connection is closed.')
        if self.busy:raise ValueError('Wait for the current connection step.')
        self.busy=True;generation=self._generation;auth_generation=self._auth_generation
        self._job_serial+=1;job=self._job_serial;self._busy_job=job
        def run():
            try:result=work(generation);error=None
            except (AuthError,AuthorizationError):result=None;error=('authorization',0)
            except RateLimitError as exc:result=None;error=('rate_limit',exc.retry_after)
            except Exception:result=None;error=('connection',0)
            self._results.put((generation,auth_generation,job,kind,result,error))
        self._executor.submit(run)
    def exchange(self,code):
        if not self.oauth:raise ValueError('Enter application details first.')
        if self.closed or self.busy:raise ValueError('Wait for the current connection step.')
        self._auth_generation+=1
        oauth=self.oauth
        self._job('tokens',lambda g:oauth.exchange(code))
        self.message='Exchanging the authorization code…'
    def _client(self):
        if not self.config or not self.tokens:raise ValueError('Authorize the application first.')
        c=self.client_factory(*self.config[:2])
        with self._lock:self._pending.add(c)
        return c
    def load_accounts(self):
        client=self._client();tokens=self.tokens
        def work(g):
            try:return tuple(a for a in client.accounts(tokens) if a.get('is_live') is False)
            finally:
                client.close()
                with self._lock:self._pending.discard(client)
        try:self._job('accounts',work)
        except Exception:
            client.close()
            with self._lock:self._pending.discard(client)
            raise
        self.message='Loading authorized demo accounts…'
    def connect(self,account,automatic=False):
        if not any(a['account_id']==account for a in self.accounts):raise ValueError('Select an authorized demo account.')
        if self.closed or self.busy:raise ValueError('Wait for the current connection step.')
        if automatic and not self._wanted:return
        # End the previous stream before opening another connection for the account.
        self.engine.disconnect()
        if self._active:self._active.close();self._active=None
        client=self._client();tokens=self.tokens
        def work(g):
            try:
                client.authorize(account,tokens)
                with self._lock:
                    if self.closed or g!=self._generation:client.close();return None
                return (account,client)
            except Exception:client.close();raise
            finally:
                with self._lock:self._pending.discard(client)
        try:self._job('connected',work)
        except Exception:
            client.close()
            with self._lock:self._pending.discard(client)
            raise
        self._wanted=True;self._desired_account=account;self._retry_at=None;self._stable_since=None
        if not automatic:self._retry_attempt=0
        self.message='Authenticating the selected demo account…'
    def poll(self):
        if self.closed:return
        self._observe_connection_state()
        while True:
            try:g,auth_g,job,kind,result,error=self._results.get_nowait()
            except queue.Empty:break
            # Disconnect cancels data jobs, but a completed OAuth renewal may
            # contain the only valid rotated token. Forget/configuration changes
            # cancel authorization results too.
            stale=(auth_g!=self._auth_generation if kind in ('tokens','refreshed') else g!=self._generation)
            if stale or self.closed:
                if kind=='connected' and result:result[1].close()
                continue
            if job==self._busy_job:self.busy=False;self._busy_job=None
            if kind=='refreshed':self._renewal_auth=None
            if error:
                category,delay=error
                if category=='authorization':
                    self._wanted=False;self._retry_at=None
                    self.message='cTrader authorization was rejected or expired. Check the application details and authorize again.'
                elif kind=='connected' and self._wanted:
                    self._schedule_retry(delay)
                else:self.message='cTrader connection step failed. Check application details, authorization and Internet access; retry.'
                if kind=='refreshed':
                    self._wanted=False;self._retry_at=None;self.engine.disconnect()
                    if self._active:self._active.close();self._active=None
                    self.message='Authorization renewal failed. Open read-only authorization again to reconnect.'
                continue
            if kind in ('tokens','refreshed'):
                self.tokens=result;self.message='Authorization ready. Load demo accounts.';self._save()
                if kind=='refreshed' and self._wanted and self._desired_account and self.accounts:
                    # cTrader may invalidate the old stream's token during our
                    # successful renewal. Retire that stream before evaluating
                    # connection state with the new token.
                    self.engine.disconnect()
                    if self._active:self._active.close();self._active=None
                    # Reauthorize with the rotated token through the same retry
                    # path, preserving any broker-imposed cooldown.
                    if self._retry_at is None:self._retry_at=self._clock()
            elif kind=='accounts':
                self.accounts=result
                self.message='Select a demo account, then Connect data.' if result else 'No authorized demo account found. Authorize your Spotware demo account.'
            elif kind=='connected' and result:
                self.account,self._active=result
                if self.mappings:self.engine.entries=self.mappings.load(self.account)
                self.engine.connect(self._active);self.message='Connected to demo market data.';self._save()
        if (not self.closed and not self.busy and self.tokens and self.oauth and
                self.tokens.expires_at.timestamp()-datetime.now(timezone.utc).timestamp()<60):
            tokens=self.tokens;oauth=self.oauth
            # One attempt per expiry. A failed refresh requires explicit authorization.
            self.tokens=None
            self._renewal_auth=self._auth_generation
            self._job('refreshed',lambda g:oauth.refresh(tokens))
            self.message='Refreshing authorization…'
        self._maintain_connection()

    def _schedule_retry(self,minimum=0):
        delay=max(minimum,min(60,2**min(self._retry_attempt+1,6)))
        self._retry_attempt+=1;self._retry_at=self._clock()+delay;self._stable_since=None
        if self._active:self._active.close();self._active=None
        self.message=f'Connection interrupted. Reconnecting in {delay:.0f} seconds…'

    def _observe_connection_state(self):
        if not self._wanted:return
        state=self.engine.connection_state
        if state=='authorization_required':
            if self._renewal_auth==self._auth_generation:return
            self._wanted=False;self._retry_at=None
            self.message='cTrader authorization ended. Open read-only authorization again.'
            return
        if state=='interrupted' and self._retry_at is None:
            self._schedule_retry(self.engine.connection_retry_after)

    def _maintain_connection(self):
        self._observe_connection_state()
        if not self._wanted or self.busy or not self.tokens:return
        state=self.engine.connection_state;now=self._clock()
        if state=='connected' and self._active and self._retry_at is None:
            if self._stable_since is None:self._stable_since=now
            if now-self._stable_since>=30:self._retry_attempt=0
            return
        if self._retry_at is not None:
            if now>=self._retry_at:
                try:self.connect(self._desired_account,automatic=True)
                except Exception:self._schedule_retry()
            else:self.message=f'Connection interrupted. Reconnecting in {max(1,int(self._retry_at-now+.999))} seconds…'

    def disconnect(self):
        self._wanted=False;self._retry_at=None;self._retry_attempt=0;self._stable_since=None
        with self._lock:
            self._generation+=1;self.busy=False
            pending=tuple(self._pending);self._pending.clear();active=self._active;self._active=None
        for c in pending:c.close()
        self.engine.disconnect()
        if active:active.close()
        self.message='Disconnected. Fresh history will be checked on reconnect.'
    def forget(self):
        self.disconnect();self.credentials.clear();self.tokens=None;self.accounts=();self.account=None
        self._auth_generation+=1
        self.message='Saved credentials removed.'
    def close(self):
        if self.closed:return
        self.closed=True;self.disconnect();self._executor.shutdown(wait=False,cancel_futures=True)

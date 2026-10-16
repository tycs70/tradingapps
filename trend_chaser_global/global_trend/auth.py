"""Read-only browser/code OAuth flow; secret-bearing failures stay private."""
from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
import math
from urllib.parse import urlencode,urlsplit,parse_qs
import requests

AUTH_URL='https://openapi.ctrader.com/apps/auth'
TOKEN_URL='https://openapi.ctrader.com/apps/token'


class AuthError(RuntimeError):pass


@dataclass(frozen=True)
class TokenBundle:
    access_token:str=field(repr=False)
    refresh_token:str=field(repr=False)
    expires_at:datetime

    def to_dict(self):
        return {'access_token':self.access_token,'refresh_token':self.refresh_token,
                'expires_at':self.expires_at.isoformat()}

    @classmethod
    def from_dict(cls,data):
        try:
            result=cls(data['access_token'],data['refresh_token'],datetime.fromisoformat(data['expires_at']))
            if (not isinstance(result.access_token,str) or not result.access_token or
                    not isinstance(result.refresh_token,str) or not result.refresh_token or
                    result.expires_at.tzinfo is None):
                raise ValueError()
            return result
        except (KeyError,TypeError,ValueError):raise AuthError('Saved authorization is unavailable; authorize again.') from None


class OAuthSession:
    def __init__(self,client_id,client_secret,redirect_uri,get=None,clock=None):
        self.client_id=str(client_id).strip();self._secret=str(client_secret).strip()
        self.redirect_uri=str(redirect_uri).strip()
        self._get=get or requests.get;self._clock=clock or (lambda:datetime.now(timezone.utc))
        try:
            uri=urlsplit(self.redirect_uri)
            valid=(uri.scheme=='https' or (uri.scheme=='http' and uri.hostname in ('localhost','127.0.0.1','::1')))
            if (not valid or not uri.hostname or uri.username or uri.password or uri.fragment or
                    any(c.isspace() for c in self.redirect_uri) or not self.client_id or not self._secret):
                raise ValueError()
        except ValueError:raise AuthError('Enter the application ID, secret and exact registered HTTPS or localhost redirect URI.') from None

    def authorization_url(self):
        return AUTH_URL+'?'+urlencode({'client_id':self.client_id,'redirect_uri':self.redirect_uri,'scope':'accounts'})

    def exchange(self,code):
        code=str(code).strip()
        if '://' in code:
            try:
                got=urlsplit(code);expected=urlsplit(self.redirect_uri)
                if (got.scheme,got.netloc,got.path or '/')!=(expected.scheme,expected.netloc,expected.path or '/'):
                    raise ValueError()
                values=parse_qs(got.query).get('code',[])
                if len(values)!=1:raise ValueError()
                code=values[0]
            except ValueError:raise AuthError('Paste the authorization code or the matching registered redirect URL.') from None
        if not code or len(code)>65536 or any(c.isspace() for c in code):
            raise AuthError('Paste a valid authorization code from the browser redirect.')
        return self._perform({'grant_type':'authorization_code','code':code,'redirect_uri':self.redirect_uri})

    def refresh(self,tokens):
        return self._perform({'grant_type':'refresh_token','refresh_token':tokens.refresh_token})

    def _perform(self,params):
        params=dict(params,client_id=self.client_id,client_secret=self._secret)
        try:
            response=self._get(TOKEN_URL,params=params,timeout=(5,20),verify=True)
            if response.status_code!=200:raise AuthError('cTrader authorization was rejected. Check the registered application and authorize again.')
            data=response.json();access=data.get('accessToken');refresh=data.get('refreshToken')
            expiry=float(data.get('expiresIn',0))
            if (not isinstance(access,str) or not access or not isinstance(refresh,str) or not refresh or
                    not math.isfinite(expiry) or not 0<expiry<=366*86400 or
                    len(access)>65536 or len(refresh)>65536):
                raise ValueError()
            return TokenBundle(access,refresh,self._clock()+timedelta(seconds=expiry))
        except requests.RequestException:
            raise AuthError('Unable to reach cTrader authorization. Check the Internet connection and retry.') from None
        except (ValueError,TypeError,AttributeError,OverflowError):
            raise AuthError('cTrader returned an incomplete authorization response. Authorize again.') from None

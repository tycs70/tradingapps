from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,parse_qs
import unittest
import requests
from global_trend.auth import OAuthSession,TokenBundle,AuthError

NOW=datetime(2026,10,15,12,tzinfo=timezone.utc)


class Response:
    def __init__(self,payload,status=200):self.payload=payload;self.status_code=status
    def json(self):return self.payload


class OAuthTest(unittest.TestCase):
    def session(self,get=None,redirect='http://localhost/'):
        return OAuthSession('test-id','PRIVATESECRET',redirect,get=get,clock=lambda:NOW)

    def test_read_only_authorization_url_encodes_redirect(self):
        url=self.session(redirect='http://localhost/callback?test=1').authorization_url()
        parsed=urlsplit(url);query=parse_qs(parsed.query)
        self.assertEqual(parsed.netloc,'openapi.ctrader.com')
        self.assertEqual(query['scope'],['accounts'])
        self.assertEqual(query['redirect_uri'],['http://localhost/callback?test=1'])
        self.assertNotIn('PRIVATESECRET',url)

    def test_code_exchange_preserves_expiry_and_redacts_token_repr(self):
        def get(url,params,**kwargs):
            self.assertEqual(url,'https://openapi.ctrader.com/apps/token')
            self.assertEqual(params['grant_type'],'authorization_code')
            self.assertEqual(params['code'],'private-code')
            self.assertIsNot(kwargs.get('verify'),False)
            return Response({'accessToken':'ACCESSPRIVATE','refreshToken':'REFRESHPRIVATE','expiresIn':3600})
        bundle=self.session(get).exchange('http://localhost/?code=private-code')
        self.assertEqual(bundle.access_token,'ACCESSPRIVATE')
        self.assertEqual(bundle.expires_at,NOW+timedelta(hours=1))
        self.assertNotIn('ACCESSPRIVATE',repr(bundle));self.assertNotIn('REFRESHPRIVATE',repr(bundle))

    def test_refresh_replaces_single_use_refresh_token(self):
        old=TokenBundle('old-access','old-refresh',NOW)
        def get(url,params,**kwargs):
            self.assertEqual(params['grant_type'],'refresh_token')
            self.assertEqual(params['refresh_token'],'old-refresh')
            return Response({'accessToken':'new-access','refreshToken':'new-refresh','expiresIn':300})
        new=self.session(get).refresh(old)
        self.assertEqual(new.refresh_token,'new-refresh');self.assertEqual(old.refresh_token,'old-refresh')

    def test_error_bodies_and_request_urls_never_reach_user(self):
        for get in [lambda *a,**k:Response({'errorCode':'PRIVATESECRET','description':'PRIVATESECRET'},400),
                    lambda *a,**k:Response({'accessToken':'PRIVATESECRET'}),
                    lambda *a,**k:Response({'accessToken':'a','refreshToken':'r','expiresIn':float('nan')})]:
            with self.assertRaises(AuthError) as caught:self.session(get).exchange('private-code')
            self.assertNotIn('PRIVATESECRET',str(caught.exception))
        def failed(*a,**k):raise requests.Timeout('PRIVATESECRET')
        with self.assertRaises(AuthError) as caught:self.session(failed).exchange('private-code')
        self.assertNotIn('PRIVATESECRET',str(caught.exception))

    def test_redirect_code_requires_configured_origin_and_path(self):
        for code in ['https://example.invalid/?code=secret','http://localhost/wrong?code=secret','']:
            with self.assertRaises(AuthError):self.session().exchange(code)

    def test_redirect_rejects_plain_http_outside_loopback(self):
        with self.assertRaises(AuthError):self.session(redirect='http://example.com/callback')

    def test_saved_token_bundle_validates_types_and_timezone(self):
        good=TokenBundle('access','refresh',NOW).to_dict()
        self.assertEqual(TokenBundle.from_dict(good).refresh_token,'refresh')
        for changes in [{'access_token':123},{'refresh_token':True},
                        {'expires_at':'2026-10-15T12:00:00'}]:
            with self.assertRaises(AuthError):TokenBundle.from_dict(dict(good,**changes))


if __name__=='__main__':unittest.main()

import base64,json,unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse,parse_qs
from unittest.mock import AsyncMock,patch
import jwt
from fastapi.testclient import TestClient
from tests import test_hosted_backend as fixtures
from src.hosted.auth import OAUTH_NONCE_COOKIE,SESSION_COOKIE

class HostedOAuthTests(unittest.TestCase):
    project_id=fixtures.HostedBackendTests.project_id
    signing_secret=fixtures.HostedBackendTests.signing_secret
    setUp=fixtures.HostedBackendTests.setUp
    tearDown=fixtures.HostedBackendTests.tearDown
    def start(self):
        self.app.state.auth_settings=replace(self.app.state.auth_settings,cookie_secure=True)
        client=TestClient(self.app,base_url='https://internal.example.test')
        response=client.post('/auth/start',headers={'Origin':'https://phone.example.test'},json={'origin':'https://phone.example.test'})
        self.assertEqual(response.status_code,200,response.text)
        query=parse_qs(urlparse(response.json()['authorize_url']).query)
        return client,response,query['state'][0]
    def test_actual_browser_origin_is_used_instead_of_internal_host(self):
        client,response,state=self.start()
        uri=parse_qs(urlparse(response.json()['authorize_url']).query)['redirectUri'][0]
        self.assertEqual(uri,'https://phone.example.test/auth/callback')
        self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.assertIn('Secure',response.headers['set-cookie'])
        self.assertIn('SameSite=lax',response.headers['set-cookie'])
    def test_missing_mismatched_or_unsafe_browser_origin_is_rejected(self):
        client=TestClient(self.app)
        for header,origin in [('', 'https://phone.example.test'),('https://other.example.test','https://phone.example.test'),('https://phone.example.test','https://phone.example.test/evil'),('null','null')]:
            response=client.post('/auth/start',headers={'Origin':header},json={'origin':origin})
            self.assertEqual(response.status_code,400)
    def test_unconfigured_get_never_guesses_the_internal_callback_host(self):
        response=TestClient(self.app).get('/auth/start',follow_redirects=False)
        self.assertEqual(response.status_code,400)
    def test_callback_preserves_signed_frontend_origin_and_consumes_nonce(self):
        client,response,state=self.start()
        identity={'openId':'isolated-oauth-test','name':'Test','email':'test@example.test'}
        with patch('src.hosted.app.exchange_code_for_identity',new=AsyncMock(return_value=identity)) as exchange:
            response=client.get('/auth/callback',params={'code':'unit-test-code','state':state},follow_redirects=False)
            self.assertEqual(response.status_code,303)
            exchange.assert_awaited_once_with('unit-test-code','https://phone.example.test/auth/callback',self.app.state.auth_settings)
        self.assertIsNone(client.cookies.get(OAUTH_NONCE_COOKIE))
        self.assertIsNotNone(client.cookies.get(SESSION_COOKIE))
        self.assertIn('SameSite=none',response.headers.get('set-cookie',''))
        replay=client.get('/auth/callback',params={'code':'unit-test-code','state':state},follow_redirects=False)
        self.assertEqual(replay.status_code,400)
    def test_changed_callback_uri_is_rejected_before_code_exchange(self):
        client,response,state=self.start()
        parsed=json.loads(base64.urlsafe_b64decode(state+'='*(-len(state)%4)))
        parsed['redirectUri']='https://attacker.example.test/auth/callback'
        tampered=base64.urlsafe_b64encode(json.dumps(parsed).encode()).decode().rstrip('=')
        with patch('src.hosted.app.exchange_code_for_identity',new=AsyncMock()) as exchange:
            result=client.get('/auth/callback',params={'code':'unit-test-code','state':tampered},follow_redirects=False)
            self.assertEqual(result.status_code,400)
            exchange.assert_not_awaited()
    def test_expired_signed_browser_binding_is_rejected(self):
        client,response,state=self.start()
        parsed=json.loads(base64.urlsafe_b64decode(state+'='*(-len(state)%4)))
        expired=jwt.encode({'appId':self.project_id,'purpose':'oauth-state','nonce':parsed['nonce'],'redirectUri':parsed['redirectUri'],'exp':datetime.now(timezone.utc)-timedelta(seconds=10)},self.signing_secret,algorithm='HS256')
        client.cookies.clear();client.cookies.set(OAUTH_NONCE_COOKIE,expired,domain='internal.example.test',path='/auth/callback')
        result=client.get('/auth/callback',params={'code':'unit-test-code','state':state},follow_redirects=False)
        self.assertEqual(result.status_code,400)
    def test_configured_canonical_origin_remains_an_allowlist(self):
        self.app.state.auth_settings=replace(self.app.state.auth_settings,public_origin='https://allowed.example.test')
        response=TestClient(self.app).post('/auth/start',headers={'Origin':'https://other.example.test'},json={'origin':'https://other.example.test'})
        self.assertEqual(response.status_code,400)

if __name__=='__main__':unittest.main()

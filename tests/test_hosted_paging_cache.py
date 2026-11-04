import gzip
import unittest
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup
import httpx
from tests import test_hosted_backend as fixtures
from src.hosted.models import HostedSavedJob
from src.hosted.source_fetch import HostedHttpClient, _HTTP_CACHE


class HostedPagingTests(unittest.TestCase):
    project_id=fixtures.HostedBackendTests.project_id
    signing_secret=fixtures.HostedBackendTests.signing_secret
    setUp=fixtures.HostedBackendTests.setUp
    tearDown=fixtures.HostedBackendTests.tearDown
    signed_session=fixtures.HostedBackendTests.signed_session
    signed_client=fixtures.HostedBackendTests.signed_client
    add_job=fixtures.HostedBackendTests.add_job

    def test_all_saved_jobs_can_be_reached_and_pages_have_one_page_parameter(self):
        client,csrf=self.signed_client('pages')
        revision=client.get('/api/profile').json()['revision']
        response=client.post('/api/profile/complete',headers={'X-CSRF-Token':csrf},json={'revision':revision,'job_profiles':['software'],'preferred_locations':['helsinki']})
        self.assertEqual(response.status_code,200)
        identifiers=[self.add_job(str(index),f'Python software developer {index}') for index in range(25)]
        with self.app.state.session_factory() as db:
            from src.hosted.models import HostedUser
            from sqlalchemy import select
            user=db.scalar(select(HostedUser).where(HostedUser.open_id=='pages'))
            db.add_all([HostedSavedJob(user_id=user.id,job_id=identifier) for identifier in identifiers]);db.commit()
        saved=BeautifulSoup(client.get('/saved').text,'html.parser')
        next_link=saved.select_one('.pagination a')
        self.assertIsNotNone(next_link)
        second=BeautifulSoup(client.get(next_link['href']).text,'html.parser')
        self.assertEqual(len(saved.select('[data-job-card]')),24)
        self.assertEqual(len(second.select('[data-job-card]')),1)
        discovered=BeautifulSoup(client.get('/discover?page=1&q=python&work=remote&work=hybrid').text,'html.parser')
        # Those filters have no fixture matches; inspect a populated page instead.
        discovered=BeautifulSoup(client.get('/discover?page=1&q=python').text,'html.parser')
        link=discovered.select_one('.pagination a')
        self.assertIsNotNone(link)
        query=parse_qs(urlparse(link['href']).query)
        self.assertEqual(query['page'],['2'])
        self.assertEqual(query['q'],['python'])


class HostedHttpCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_compressed_network_response_is_reused_without_double_decoding(self):
        calls=[]
        def handler(request):
            calls.append(request.url)
            return httpx.Response(200,content=gzip.compress(b'public listing'),headers={'Content-Encoding':'gzip'})
        _HTTP_CACHE.clear()
        async with HostedHttpClient(transport=httpx.MockTransport(handler)) as client:
            first=await client.get('https://example.test/compressed-cache-test')
            second=await client.get('https://example.test/compressed-cache-test')
        self.assertEqual(first.text,'public listing')
        self.assertEqual(second.text,'public listing')
        self.assertEqual(len(calls),1)
        _HTTP_CACHE.clear()


if __name__=='__main__':
    unittest.main()

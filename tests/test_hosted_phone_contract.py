import unittest
from datetime import datetime,timedelta,timezone
from bs4 import BeautifulSoup
from sqlalchemy import select
from tests import test_hosted_backend as fixtures
from src.hosted.models import HostedJob

class HostedPhoneContractTests(unittest.TestCase):
    project_id=fixtures.HostedBackendTests.project_id
    signing_secret=fixtures.HostedBackendTests.signing_secret
    setUp=fixtures.HostedBackendTests.setUp
    tearDown=fixtures.HostedBackendTests.tearDown
    signed_session=fixtures.HostedBackendTests.signed_session
    signed_client=fixtures.HostedBackendTests.signed_client
    add_job=fixtures.HostedBackendTests.add_job

    def test_old_listing_leaves_discovery_but_bookmark_survives_new_preferences(self):
        client,csrf=self.signed_client('retained')
        self.assertEqual(client.post('/api/profile/complete',headers={'X-CSRF-Token':csrf},json={'revision':0,'job_profiles':['software'],'preferred_locations':['helsinki']}).status_code,200)
        identifier=self.add_job('retained','Python developer')
        self.assertEqual(client.post(f'/api/jobs/{identifier}/save',headers={'X-CSRF-Token':csrf},json={'saved':True}).status_code,200)
        with self.app.state.session_factory() as db:
            db.get(HostedJob,identifier).updated_at=datetime.now(timezone.utc)-timedelta(days=10);db.commit()
        self.assertEqual(client.get('/api/jobs').json()['total'],0)
        revision=client.get('/api/profile').json()['revision']
        response=client.post('/api/profile/complete',headers={'X-CSRF-Token':csrf},json={'revision':revision,'job_profiles':['marketing'],'preferred_locations':['bengaluru'],'remote_ok':False,'hybrid_ok':False})
        self.assertEqual(response.status_code,200)
        saved=BeautifulSoup(client.get('/saved').text,'html.parser')
        self.assertEqual(len(saved.select('[data-job-card]')),1)
        detail=client.get(f'/jobs/{identifier}')
        self.assertEqual(detail.status_code,200)
        self.assertIn('has not been seen in recent source checks',detail.text)

    def test_source_progress_is_outside_the_hidden_desktop_sidebar(self):
        client,csrf=self.signed_client('phone')
        client.post('/api/profile/complete',headers={'X-CSRF-Token':csrf},json={'revision':0,'job_profiles':['software']})
        page=BeautifulSoup(client.get('/discover').text,'html.parser')
        self.assertEqual(len(page.select('#source-health')),1)
        self.assertIsNone(page.select_one('#source-health').find_parent('aside'))
        self.assertIsNone(page.select_one('#refresh-status').find_parent('aside'))
        self.assertIsNotNone(page.select_one('#filter-source option[value="companycareers"]'))
        self.assertEqual(page.select_one('#filter-source option[value="academicwork"]').get_text(),'Academic Work')

if __name__=='__main__':unittest.main()

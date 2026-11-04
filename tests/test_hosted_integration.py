"""Hosted UI/API regressions. Temporary SQLite and test-signed JWTs only."""
import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from tests import test_hosted_backend as fixtures
from src.hosted.models import HostedJob


class HostedIntegrationTests(unittest.TestCase):
    project_id = fixtures.HostedBackendTests.project_id
    signing_secret = fixtures.HostedBackendTests.signing_secret
    setUp = fixtures.HostedBackendTests.setUp
    tearDown = fixtures.HostedBackendTests.tearDown
    signed_session = fixtures.HostedBackendTests.signed_session
    signed_client = fixtures.HostedBackendTests.signed_client
    add_job = fixtures.HostedBackendTests.add_job

    def complete(self, client, csrf, fields=None, places=None):
        revision = client.get('/api/profile').json()['revision']
        response = client.post('/api/profile/complete', headers={'X-CSRF-Token': csrf}, json={
            'revision': revision, 'job_profiles': fields or ['software'],
            'preferred_locations': places or ['helsinki'], 'preferred_tech': ['python'],
            'experience_level': 'junior', 'remote_ok': True, 'hybrid_ok': True,
            'alert_threshold': 0,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['profile']

    def test_all_hosted_pages_render_with_safe_json_and_private_cache_headers(self):
        job_id = self.add_job('html-safe', 'Python software developer', '<script>alert(1)</script> mentoring')
        client, csrf = self.signed_client('reader')
        self.complete(client, csrf)
        client.post(f'/api/jobs/{job_id}/save', headers={'X-CSRF-Token': csrf}, json={'saved': True})
        client.post(f'/api/jobs/{job_id}/application', headers={'X-CSRF-Token': csrf}, json={'status': 'saved', 'notes': 'A private note'})
        for path in ['/', '/discover', '/saved', '/tracker', '/profile', '/onboarding', f'/jobs/{job_id}']:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, response.text[:800])
                self.assertIn('private, no-store', response.headers.get('cache-control',''))
                self.assertNotIn('<script>alert(1)</script>', response.text)
                dom = BeautifulSoup(response.text, 'html.parser')
                self.assertIsNotNone(dom.select_one('main#main'))
                self.assertIsNotNone(dom.select_one('script#app-config[type="application/json"]'))
        self.assertIn('A private note', client.get('/tracker').text)
        offline = TestClient(self.app).get('/offline')
        self.assertEqual(offline.status_code, 200)
        self.assertNotIn('A private note', offline.text)

    def test_real_browser_dates_save_and_clear(self):
        client, csrf = self.signed_client('dates')
        job_id = self.add_job('dates', 'Python developer')
        response = client.post(f'/api/jobs/{job_id}/application', headers={'X-CSRF-Token': csrf}, json={
            'status': 'applied', 'applied_at': '2026-10-30', 'closing_date': '2026-11-15', 'notes': 'Keep this', 'outcome': 'Follow up',
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['application']['applied_at'].startswith('2026-10-30'))
        cleared = client.post(f'/api/jobs/{job_id}/application', headers={'X-CSRF-Token': csrf}, json={
            'status': 'interview', 'applied_at': '2026-10-30', 'closing_date': None, 'notes': 'Keep this', 'outcome': 'Follow up',
        })
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()['application']['closing_date'])
        self.assertEqual(cleared.json()['application']['notes'], 'Keep this')

    def test_both_work_styles_and_multiple_cities_are_or_filters(self):
        client, csrf = self.signed_client('filters')
        self.complete(client, csrf, places=['finland'])
        helsinki = self.add_job('hki', 'Python software developer', location='Helsinki')
        tampere = self.add_job('tre', 'Python software developer', location='Tampere')
        self.add_job('oulu', 'Python software developer', location='Oulu')
        with self.app.state.session_factory() as db:
            db.get(HostedJob, helsinki).remote = True
            db.get(HostedJob, tampere).hybrid = True
            db.commit()
        url = '/api/jobs?location=helsinki,tampere&work=remote&work=hybrid&sort=newest'
        response = client.get(url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['total'], 2)
        page = client.get('/discover?work=remote&work=hybrid&min_score=0&sort=newest')
        self.assertEqual(page.status_code, 200, page.text[:400])
        dom = BeautifulSoup(page.text, 'html.parser')
        self.assertEqual(len(dom.select('input[name=work][checked]')), 2)
        self.assertEqual(dom.select_one('#sort option[selected]')['value'], 'newest')
        self.assertEqual(dom.select_one('#filter-score option[selected]')['value'], '0')

    def test_draft_conflict_cannot_overwrite_another_device(self):
        client, csrf = self.signed_client('draft')
        revision = client.get('/api/profile').json()['revision']
        first = client.post('/api/profile/draft', headers={'X-CSRF-Token': csrf}, json={'revision': revision, 'step': 3, 'job_profiles': ['software']})
        self.assertEqual(first.status_code, 200)
        stale = client.post('/api/profile/draft', headers={'X-CSRF-Token': csrf}, json={'revision': revision, 'step': 4, 'job_profiles': ['marketing']})
        self.assertEqual(stale.status_code, 409)
        stored = client.get('/api/profile').json()
        self.assertEqual(stored['draft']['job_profiles'], ['software'])
        self.assertFalse(stored['onboarding_completed'])

    def test_selected_fields_filter_unrelated_jobs_but_keep_saved_history(self):
        client, csrf = self.signed_client('fields')
        self.complete(client, csrf, fields=['software'])
        tech_id = self.add_job('tech', 'Python software developer', 'Python skills')
        other_id = self.add_job('other', 'Sales representative', 'Customer accounts')
        client.post(f'/api/jobs/{other_id}/save', headers={'X-CSRF-Token': csrf}, json={'saved': True})
        listed = client.get('/api/jobs').json()
        self.assertEqual([job['id'] for job in listed['jobs']], [tech_id])
        self.assertIn('Sales representative', client.get('/saved').text)

    def test_public_manifest_icons_fonts_and_route_manifest(self):
        client = TestClient(self.app)
        route_response = client.get('/manus-routes.json')
        self.assertEqual(route_response.status_code, 200)
        document = route_response.json()
        self.assertEqual(set(document), {'routes'})
        paths = {row['path'] for row in document['routes']}
        self.assertIn('/jobs/:job_id', paths)
        self.assertNotIn('/api/scheduled/refresh', paths)
        manifest = client.get('/manifest.webmanifest')
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json()['display'], 'standalone')
        for icon in manifest.json()['icons']:
            self.assertEqual(client.get(icon['src']).status_code, 200)
        self.assertEqual(client.get('/static/fonts/inter-var.woff2').status_code, 200)
        worker = client.get('/service-worker.js')
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker.headers['service-worker-allowed'], '/')
        self.assertEqual(client.get('/health').status_code, 200)


if __name__ == '__main__':
    unittest.main()

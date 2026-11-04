"""App regressions with an isolated SQLite database; no live source requests or alerts."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Prevent import-time table creation from touching the user's database.
QA_DIR = Path(__file__).resolve().parents[1] / '.work' / 'qa'
QA_DIR.mkdir(parents=True, exist_ok=True)
os.environ['DATABASE_URL'] = f'sqlite:///{QA_DIR / "test-import.db"}'
os.environ['APP_LOG_FILE'] = str(QA_DIR / 'test-application.log')

from src import main
from src.alerts import get_alert_candidates
from src.config import Settings
from src.fetch_control import FetchController
from src.models import Application, Base, Job
from src.preferences import get_preferences, set_preferences


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()
        set_preferences(self.db, {'onboarding_completed': True})
        self.db.add_all([
            Job(source='jobly', source_id='1', title='Junior Python Developer', company='Alpha Oy', location='Helsinki', score=80, remote=True, date_posted=datetime(2026, 10, 20)),
            Job(source='academicwork', source_id='2', title='Data Analyst', company='Beta Oy', location='Oulu', score=65, hybrid=True, date_posted=datetime(2026, 10, 21)),
            Job(source='thehub', source_id='3', title='Frontend Developer', company='Gamma Oy', location='Espoo', score=55, date_posted=datetime(2026, 10, 22)),
            Job(source='jobly', source_id='4', title='Software Trainee', company='Delta Oy', location='Helsinki', score=45, hidden=True),
        ])
        self.db.commit()
        for job in self.db.query(Job):
            job.url = 'https://example.invalid/jobs/' + job.source_id
        self.db.commit()

        def db_override():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[main.get_db] = db_override
        self.session_patch = patch.object(main, 'SessionLocal', self.sessions)
        self.session_patch.start()
        self.schedule_patch = patch.object(main.scheduler, 'add_job')
        self.schedule_patch.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://testserver', follow_redirects=False)

    async def asyncTearDown(self):
        await self.client.aclose()
        main.app.dependency_overrides.clear()
        self.session_patch.stop()
        self.schedule_patch.stop()
        self.db.close()
        self.engine.dispose()

    async def test_onboarding_json_cannot_break_html_or_expose_javascript(self):
        malicious = 'sql " onmouseover="bad() </script><script>bad()</script>'
        set_preferences(self.db, {'preferred_tech': [malicious], 'alert_threshold': 0})
        response = await self.client.get('/onboarding')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertEqual(soup.find(attrs={'x-data': 'onboarding'})['x-data'], 'onboarding')
        config = json.loads(soup.find(id='onboarding-config').string)
        self.assertEqual(config['prefs']['preferred_tech'], [malicious])
        self.assertEqual(config['prefs']['alert_threshold'], 0)
        self.assertNotIn('toggleTrack(t)', soup.get_text())
        self.assertNotIn('bad()', [script.string for script in soup.find_all('script') if script.string == 'bad()'])
        self.assertLess(response.text.index('/static/js/onboarding.js'), response.text.index('/static/vendor/alpine.min.js'))

    async def test_preferences_attribute_preserves_complete_json(self):
        set_preferences(self.db, {'preferred_locations': ['helsinki', 'oulu']})
        soup = BeautifulSoup((await self.client.get('/preferences')).text, 'html.parser')
        self.assertEqual(soup.find('form', action='/preferences')['x-data'], '{ towns: ["helsinki", "oulu"] }')

    async def test_invalid_profile_payloads_never_poison_preferences(self):
        before = get_preferences(self.db)
        for payload in [[], None, {'preferred_tech': 'python'}, {'remote_ok': 'false'}, {'alert_threshold': 101}, {'alert_threshold': -1}, {'job_profiles': ['bogus']}, {'experience_level': 'senior'}, {'preferred_locations': None}]:
            with self.subTest(payload=payload):
                response = await self.client.post('/api/profile', content=json.dumps(payload), headers={'Content-Type': 'application/json'})
                self.assertEqual(response.status_code, 400)
        self.db.expire_all()
        self.assertEqual(get_preferences(self.db), before)

    async def test_profile_round_trip_normalizes_lists_and_preserves_zero(self):
        response = await self.client.post('/api/profile', json={'job_profiles': ['software'], 'preferred_tech': [' Python ', 'python'], 'preferred_locations': ['Oulu'], 'alert_threshold': 0, 'remote_ok': False})
        self.assertEqual(response.status_code, 200)
        profile = response.json()['profile']
        self.assertEqual(profile['preferred_tech'], ['python'])
        self.assertEqual(profile['alert_threshold'], 0)
        self.assertFalse(profile['remote_ok'])
        self.assertEqual(profile['preferred_locations'], ['oulu'])
        self.assertIsNotNone(datetime.fromisoformat(profile['profile_updated_at']).tzinfo)
        self.assertEqual((await self.client.get('/api/profile')).json(), profile)

    async def test_stale_local_sync_cannot_overwrite_new_server_preferences(self):
        await self.client.post('/api/profile', json={'preferred_tech': ['rust']})
        stale = await self.client.post('/api/profile', json={'preferred_tech': ['python'], 'profile_updated_at': '2020-01-01T00:00:00Z'})
        self.assertTrue(stale.json()['stale'])
        self.assertEqual(stale.json()['profile']['preferred_tech'], ['rust'])

    async def test_legacy_role_tracks_update_the_new_profile_key(self):
        response = await self.client.post('/api/profile', json={'role_tracks': ['marketing']})
        self.assertEqual(response.json()['profile']['job_profiles'], ['marketing'])

    async def test_preferences_form_stamps_sync_time_and_rejects_invalid_threshold(self):
        response = await self.client.post('/preferences', data={'preferred_tech': 'Go, SQL', 'preferred_locations': 'Oulu, Helsinki', 'alert_threshold': '0'})
        self.assertEqual(response.status_code, 303)
        profile = (await self.client.get('/api/profile')).json()
        self.assertEqual(profile['preferred_tech'], ['go', 'sql'])
        self.assertTrue(profile['profile_updated_at'])
        self.assertEqual(profile['alert_threshold'], 0)
        invalid = await self.client.post('/preferences', data={'alert_threshold': 'garbage'})
        self.assertEqual(invalid.status_code, 422)

    async def test_repeated_and_csv_source_checkboxes_are_equivalent(self):
        repeated = await self.client.get('/?sources=jobly&sources=academicwork')
        csv = await self.client.get('/?sources=jobly,academicwork')
        for response in (repeated, csv):
            soup = BeautifulSoup(response.text, 'html.parser')
            self.assertEqual(len(soup.select('article.job-card')), 2)
            self.assertIn('Junior Python Developer', response.text)
            self.assertIn('Data Analyst', response.text)
            self.assertNotIn('Frontend Developer', response.text)

    async def test_multiple_cities_include_oulu(self):
        response = await self.client.get('/?locations=helsinki&locations=oulu')
        self.assertEqual(len(BeautifulSoup(response.text, 'html.parser').select('article.job-card')), 2)
        self.assertIn('Data Analyst', response.text)
        self.assertIn('oulu', (await self.client.get('/api/locations')).json())

    async def test_both_work_setups_apply_and_sort_survives_filter_submission(self):
        response = await self.client.get('/?work=remote&work=hybrid&sort=company')
        soup = BeautifulSoup(response.text, 'html.parser')
        self.assertEqual(len(soup.select('article.job-card')), 2)
        self.assertEqual(soup.find('input', attrs={'name': 'sort'})['value'], 'company')

    async def test_tracker_saved_visible_applied_hidden_and_dates_can_be_cleared(self):
        response = await self.client.post('/applications', data={'job_id': '1', 'status': 'saved', 'applied_at': '2026-10-20', 'notes': 'Follow up'})
        self.assertEqual(response.status_code, 303)
        self.assertIn('Junior Python Developer', (await self.client.get('/')).text)
        self.assertIn('Follow up', (await self.client.get('/applications')).text)
        with self.sessions() as db:
            application_id = db.query(Application).one().id
        await self.client.post(f'/applications/{application_id}', data={'status': 'applied', 'notes': 'Sent', 'applied_at': '', 'closing_date': ''})
        self.assertNotIn('Junior Python Developer', (await self.client.get('/')).text)
        self.assertIn('Junior Python Developer', (await self.client.get('/?tracked=all')).text)
        with self.sessions() as db:
            application = db.query(Application).one()
            self.assertIsNone(application.applied_at)
            self.assertEqual(application.notes, 'Sent')
        await self.client.post(f'/applications/{application_id}/delete')
        self.assertIn('Junior Python Developer', (await self.client.get('/')).text)

    async def test_hide_and_missing_jobs(self):
        self.assertEqual((await self.client.post('/hide/999')).status_code, 404)
        self.assertTrue((await self.client.post('/hide/1')).json()['ok'])
        self.assertNotIn('Junior Python Developer', (await self.client.get('/')).text)

    async def test_api_pagination_bounds_and_cache_headers(self):
        response = await self.client.get('/api/jobs?skip=1&limit=1')
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        for query in ['skip=-1', 'limit=0', 'limit=501', 'min_score=101']:
            self.assertEqual((await self.client.get('/api/jobs?' + query)).status_code, 422)
        worker = await self.client.get('/static/sw.js')
        self.assertEqual(worker.headers['service-worker-allowed'], '/')
        self.assertEqual((await self.client.get('/health')).json()['ok'], True)

    async def test_selected_nontech_field_filters_old_tech_jobs_before_pagination(self):
        self.db.add(Job(source='jobly', source_id='marketing', title='Marketing Specialist', company='Business Oy', location='Helsinki', score=70))
        self.db.commit()
        await self.client.post('/api/profile', json={'job_profiles': ['marketing']})
        jobs = (await self.client.get('/api/jobs')).json()
        self.assertEqual([job['title'] for job in jobs], ['Marketing Specialist'])
        page = (await self.client.get('/')).text
        self.assertIn('Marketing Specialist', page)
        self.assertNotIn('Junior Python Developer', page)

    async def test_custom_preferred_city_reaches_the_feed(self):
        self.db.add(Job(source='jobly', source_id='kuopio', title='Junior Software Developer Kuopio', company='North Oy', location='Kuopio', score=70))
        self.db.commit()
        await self.client.post('/api/profile', json={'preferred_locations': ['Kuopio']})
        self.assertIn('Junior Software Developer Kuopio', (await self.client.get('/')).text)

    async def test_card_tracking_form_preserves_existing_notes_and_status(self):
        await self.client.post('/applications', data={'job_id': '1', 'status': 'applied', 'notes': 'Existing note', 'applied_at': '2026-10-20'})
        soup = BeautifulSoup((await self.client.get('/?tracked=all')).text, 'html.parser')
        form = soup.select_one('#job-1 form')
        self.assertEqual(form.select_one('option[selected]')['value'], 'applied')
        self.assertEqual(form.select_one('[name="notes"]')['value'], 'Existing note')
        self.assertEqual(form.select_one('[name="applied_at"]')['value'], '2026-10-20')

    async def test_alerts_respect_saved_threshold(self):
        set_preferences(self.db, {'alert_threshold': 75})
        self.assertEqual([job.title for job in get_alert_candidates(self.db)], ['Junior Python Developer'])

    async def test_manual_refresh_returns_accepted_immediately_and_single_flights(self):
        gate = asyncio.Event()
        async def runner():
            await gate.wait()
            return {'ok': True, 'new_jobs': 2}
        controller = FetchController(runner)
        with patch.object(main, 'fetch_controller', controller):
            first = await self.client.post('/fetch')
            second = await self.client.post('/fetch')
            self.assertEqual(first.status_code, 202)
            self.assertTrue(first.json()['started'])
            self.assertFalse(second.json()['started'])
            self.assertEqual((await self.client.get('/api/fetch/status')).json()['status'], 'running')
            gate.set()
            await controller.task
            self.assertEqual((await self.client.get('/api/fetch/status')).json()['new_jobs'], 2)


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failures_are_not_reported_as_success(self):
        async def runner():
            raise RuntimeError('fixture failure')
        controller = FetchController(runner)
        result = await controller.run()
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'error')

    async def test_shutdown_cancels_an_outstanding_fetch(self):
        async def runner():
            await asyncio.Event().wait()
        controller = FetchController(runner)
        controller.start()
        await asyncio.sleep(0)
        await controller.close()
        self.assertTrue(controller.task.done())
        self.assertEqual(controller.snapshot()['status'], 'cancelled')


class ConfigTests(unittest.TestCase):
    def test_safe_example_environment_loads_csv_lists(self):
        settings = Settings(_env_file=Path(__file__).resolve().parents[1] / '.env.example')
        self.assertIn('python', settings.default_preferred_tech)
        self.assertIn('oulu', settings.default_preferred_locations)
        self.assertFalse(settings.smtp_host)
        self.assertFalse(settings.discord_webhook_url)
        self.assertFalse(settings.enable_linkedin)


if __name__ == '__main__':
    unittest.main()

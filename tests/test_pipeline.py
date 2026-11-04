"""Offline pipeline regressions: sources are mocked and SQLite is in-memory."""
import asyncio
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import scraper
from src.models import Application, Base, Job


class PipelineDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def job(self, source, source_id, location='Helsinki', **kwargs):
        job = Job(source=source, source_id=source_id, title='Junior Developer', company='Example Oy',
                  location=location, url='https://example.invalid/jobs/' + source_id, **kwargs)
        self.db.add(job)
        self.db.flush()
        return job

    def test_repeated_id_in_one_fetch_batch_creates_one_row(self):
        row = {'source': 'jobly', 'source_id': 'same', 'title': 'Junior Developer', 'company': 'Example Oy',
               'location': 'Helsinki', 'description': 'Python and mentoring', 'url': 'https://example.invalid/job'}
        counts = scraper.save_jobs(self.db, [row, row.copy()])
        self.assertEqual(counts, (1, 1))
        self.assertEqual(self.db.query(Job).count(), 1)

    def test_cross_source_dedupe_keeps_distinct_cities(self):
        self.job('jobly', 'helsinki', 'Helsinki')
        self.job('companycareers', 'oulu', 'Oulu')
        self.db.commit()
        self.assertEqual(scraper.dedupe_jobs(self.db), 0)
        self.assertEqual(self.db.query(Job).count(), 2)

    def test_matching_duplicates_keep_employer_link(self):
        self.job('jobly', 'board')
        self.job('companycareers', 'employer')
        self.db.commit()
        self.assertEqual(scraper.dedupe_jobs(self.db), 1)
        self.assertEqual(self.db.query(Job).one().source, 'companycareers')

    def test_tracked_duplicate_survives_even_when_the_link_is_lower_priority(self):
        tracked = self.job('jobly', 'board')
        self.db.add(Application(job_id=tracked.id, status='applied', notes='Keep this'))
        self.job('companycareers', 'employer')
        self.db.commit()
        scraper.dedupe_jobs(self.db)
        self.assertEqual(self.db.query(Application).one().notes, 'Keep this')
        self.assertEqual(self.db.query(Application).one().job.source_id, 'board')

    def test_stale_pruning_preserves_tracked_applications(self):
        old = datetime.utcnow() - timedelta(days=10)
        tracked = self.job('jobly', 'tracked', updated_at=old)
        self.db.add(Application(job_id=tracked.id, status='interview'))
        self.job('jobly', 'stale', updated_at=old)
        self.db.commit()
        removed = scraper.prune_stale_jobs(self.db, {'jobly': {'current'}})
        self.assertEqual(removed, 1)
        self.assertEqual(self.db.query(Job).one().source_id, 'tracked')
        self.assertEqual(self.db.query(Application).one().status, 'interview')


class _FakeClient:
    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


class _Snapshot:
    def __init__(self, previous):
        self.previous = previous
        self.updates = []
    def get(self, source): return self.previous
    def update(self, source, items): self.updates.append((source, items))


class _Source:
    name = 'fixture'
    def __init__(self, slow=False): self.slow = slow
    async def fetch(self, client):
        if self.slow:
            await asyncio.Event().wait()
        return []
    def normalize(self, item): return item


class PipelineFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_fallback_respects_current_profile_and_does_not_renew_age(self):
        snapshot = _Snapshot([
            {'source': 'fixture', 'source_id': 'tech', 'title': 'Software Developer', 'description': 'Python'},
            {'source': 'fixture', 'source_id': 'business', 'title': 'Marketing Specialist', 'description': 'marketing campaigns'},
        ])
        with patch.object(scraper, 'SOURCES', [_Source()]), patch.object(scraper, 'CachedAsyncClient', _FakeClient), patch.object(scraper, 'snapshot_cache', snapshot):
            jobs, succeeded = await scraper.fetch_all_jobs(['marketing'])
        self.assertEqual([job['source_id'] for job in jobs], ['business'])
        self.assertEqual(succeeded, {})
        self.assertEqual(snapshot.updates, [])
        self.assertEqual(scraper.SOURCE_STATUS['fixture']['status'], 'cached')

    async def test_a_stalled_source_times_out_and_reports_failure(self):
        snapshot = _Snapshot([])
        with patch.object(scraper, 'SOURCES', [_Source(slow=True)]), patch.object(scraper, 'CachedAsyncClient', _FakeClient), patch.object(scraper, 'snapshot_cache', snapshot), patch.object(scraper.settings, 'source_timeout_seconds', 0.01):
            jobs, succeeded = await asyncio.wait_for(scraper.fetch_all_jobs(), timeout=1)
        self.assertEqual(jobs, [])
        self.assertEqual(succeeded, {})
        self.assertEqual(scraper.SOURCE_STATUS['fixture']['status'], 'error')


if __name__ == '__main__':
    unittest.main()

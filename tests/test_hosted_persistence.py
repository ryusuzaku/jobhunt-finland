"""Atomic profile revisions and source persistence: isolated SQLite only."""
import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from tests import test_hosted_backend as fixtures
from src.hosted.models import HostedProfile, HostedFetchRun, HostedJob
from src.hosted.queries import _persist_refresh, acquire_refresh


class HostedPersistenceTests(unittest.TestCase):
    project_id=fixtures.HostedBackendTests.project_id
    signing_secret=fixtures.HostedBackendTests.signing_secret
    setUp=fixtures.HostedBackendTests.setUp
    tearDown=fixtures.HostedBackendTests.tearDown
    signed_session=fixtures.HostedBackendTests.signed_session
    signed_client=fixtures.HostedBackendTests.signed_client

    def test_simultaneous_profile_writers_cannot_both_commit(self):
        self.signed_client('atomic')
        factory=self.app.state.session_factory
        with factory() as first, factory() as second:
            a=first.scalar(select(HostedProfile)); b=second.scalar(select(HostedProfile))
            a.preferred_tech=['python']; a.revision+=1; first.commit()
            b.preferred_tech=['go']; b.revision+=1
            with self.assertRaises(StaleDataError):
                second.commit()
            second.rollback()
        with factory() as db:
            profile=db.scalar(select(HostedProfile))
            self.assertEqual(profile.preferred_tech,['python'])
            self.assertEqual(profile.revision,1)

    def run_rows(self, rows, states):
        factory=self.app.state.session_factory
        with factory() as db:
            run,started=acquire_refresh(db)
            self.assertTrue(started)
            identifier=run.id
        return _persist_refresh(identifier,rows,states,factory)

    def test_batch_duplicate_ids_create_one_listing_and_keep_creation_time(self):
        row={'source':'unit','source_id':'same','title':'Python developer','company':'Public Co','location':'Helsinki','url':'https://example.test/job','description':'Python mentoring'}
        result=self.run_rows([row,row],{'unit':{'status':'fresh','count':2}})
        self.assertTrue(result['ok']); self.assertEqual(result['new_jobs'],1)
        with self.app.state.session_factory() as db:
            records=db.scalars(select(HostedJob)).all()
            self.assertEqual(len(records),1); created=records[0].created_at
        updated={**row,'title':'Python developer — updated'}
        result=self.run_rows([updated],{'unit':{'status':'fresh','count':1}})
        self.assertEqual(result['updated_jobs'],1)
        with self.app.state.session_factory() as db:
            job=db.scalar(select(HostedJob))
            self.assertEqual(job.created_at,created)
            self.assertEqual(job.title,updated['title'])

    def test_cached_fallback_does_not_make_an_old_listing_fresh(self):
        row={'source':'unit','source_id':'old','title':'Python developer','location':'Helsinki','description':'Public listing'}
        self.run_rows([row],{'unit':{'status':'fresh','count':1}})
        old=datetime.now(timezone.utc)-timedelta(days=3)
        with self.app.state.session_factory() as db:
            db.scalar(select(HostedJob)).updated_at=old; db.commit()
        self.run_rows([row],{'unit':{'status':'cached','count':1}})
        with self.app.state.session_factory() as db:
            updated=db.scalar(select(HostedJob)).updated_at
            self.assertLess(updated.replace(tzinfo=timezone.utc),datetime.now(timezone.utc)-timedelta(days=2))

    def test_all_source_failures_are_not_reported_as_a_success(self):
        result=self.run_rows([],{'unit':{'status':'error','count':0,'error':'SourceLayoutError'}})
        self.assertFalse(result['ok']); self.assertEqual(result['status'],'error')


if __name__=='__main__':
    unittest.main()

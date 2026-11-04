"""SQLite concurrency regression in a temporary project-owned database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.work' / 'qa'
QA.mkdir(parents=True, exist_ok=True)
os.environ['DATABASE_URL'] = f'sqlite:///{QA / "concurrency-import.db"}'
os.environ['APP_LOG_FILE'] = str(QA / 'concurrency.log')

from src import main
from src.models import Base, Job, sqlite_connection_settings
from src.preferences import set_preferences


class SQLiteConcurrencyTests(unittest.TestCase):
    def test_multibatch_rescore_allows_readers_and_preserves_source_freshness(self):
        with tempfile.TemporaryDirectory(prefix='sqlite-concurrency-', dir=QA) as directory:
            path = Path(directory) / 'jobs.db'
            engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False, 'timeout': 10})
            event.listen(engine, 'connect', sqlite_connection_settings)
            Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine, autoflush=False)
            old = datetime(2020, 1, 1)
            with sessions() as db:
                set_preferences(db, {'preferred_tech': ['python']})
                for index in range(205):
                    db.add(Job(source='fixture', source_id=str(index), title=f'Junior Software Developer {index}',
                               company='Fixture Oy', location='Helsinki', description='Python mentoring', updated_at=old))
                db.commit()
            scoring_started = threading.Event()
            original_score = main.score_job
            def slowed_score(**kwargs):
                scoring_started.set()
                time.sleep(0.001)
                return original_score(**kwargs)
            try:
                with patch.object(main, 'SessionLocal', sessions), patch.object(main, 'score_job', slowed_score), ThreadPoolExecutor(max_workers=2) as pool:
                    writing = pool.submit(main._rescore_job_rows)
                    self.assertTrue(scoring_started.wait(5))
                    for _ in range(5):
                        with sessions() as db:
                            self.assertEqual(db.query(Job).count(), 205)
                    self.assertEqual(writing.result(timeout=10), 205)
                with sessions() as db:
                    self.assertEqual(db.query(Job).filter(Job.updated_at != old).count(), 0)
                    self.assertGreater(db.query(Job).first().score, 0)
            finally:
                engine.dispose()


if __name__ == '__main__':
    unittest.main()

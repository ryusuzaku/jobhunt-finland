"""Initialize the hosted-only schema. Never imports or edits data/jobs.db.

Run once with the managed DATABASE_URL injected. SQLAlchemy create_all is additive;
column drift is checked and must be handled by an explicit future migration.
"""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect
from src.hosted.models import Base, create_hosted_engine, create_schema


def main():
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith(('mysql://', 'mysql+pymysql://')):
        raise SystemExit('Managed MySQL DATABASE_URL is required. No local SQLite fallback will be initialized.')
    engine = create_hosted_engine(url)
    try:
        if any(not table.startswith('jh_') for table in Base.metadata.tables):
            raise SystemExit('Refusing schema preparation outside hosted jh_ tables.')
        create_schema(engine)
        inspector = inspect(engine)
        for name, table in Base.metadata.tables.items():
            actual = {column['name'] for column in inspector.get_columns(name)}
            missing = {column.name for column in table.columns} - actual
            if missing:
                raise SystemExit(f'Explicit schema migration required for {name}: missing {sorted(missing)}')
        print('Hosted schema ready:', ', '.join(sorted(Base.metadata.tables)))
        print('Local SQLite profile/application data was not read or imported.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

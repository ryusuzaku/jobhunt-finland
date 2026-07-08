# One-time migration helper for SQLite.
# Adds any missing tables/columns defined in src.models without dropping existing data.

from src.models import Base, engine


def main():
    print("Running migrations...")
    Base.metadata.create_all(bind=engine)
    print("Done. New tables/columns created if they were missing.")


if __name__ == "__main__":
    main()

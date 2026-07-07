from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, Boolean, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import settings

Base = declarative_base()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), default="duunitori", index=True)
    source_id = Column(String(255), index=True)  # stable id within source
    title = Column(String(500))
    company = Column(String(255), index=True)
    location = Column(String(255), index=True)
    description = Column(Text)
    url = Column(String(1000))
    date_posted = Column(DateTime)

    # Salary
    salary_text = Column(String(500), nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), nullable=True)
    salary_period = Column(String(20), nullable=True)  # month, hour, year

    # Work arrangement
    remote = Column(Boolean, default=False)
    hybrid = Column(Boolean, default=False)

    # Company signals (populated when available, mainly from The Hub)
    company_size = Column(String(50), nullable=True)  # e.g. "1-10"
    company_founded = Column(String(20), nullable=True)
    company_website = Column(String(500), nullable=True)
    company_perks = Column(JSON, default=list)

    # Scoring
    score = Column(Float, default=0.0)
    learning_score = Column(Float, default=0.0)
    worklife_score = Column(Float, default=0.0)
    tech_score = Column(Float, default=0.0)
    company_score = Column(Float, default=0.0)

    # Flags
    is_new = Column(Boolean, default=True)
    alerted = Column(Boolean, default=False)
    hidden = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Preference(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, index=True)
    value = Column(Text)  # stored as JSON string
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Hosted JobHunt persistence.

This module intentionally does not import the legacy SQLite models or create tables
at import time.  The managed MySQL database is shared by development and release,
so schema creation is an explicit deployment/migration action.  Tests may call
``create_schema`` against an isolated SQLite engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import json
import ssl

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for hosted-only, additive ``jh_`` tables."""


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp suitable for hosted records."""
    return datetime.now(timezone.utc)


def create_hosted_engine(database_url: str) -> Engine:
    """Create a MySQL-compatible SQLAlchemy engine without touching legacy DB state."""
    if not database_url:
        raise ValueError("DATABASE_URL is required for hosted storage")
    # Managed URLs are commonly published as mysql://. SQLAlchemy otherwise
    # selects MySQLdb for that spelling; this project uses the installed
    # PyMySQL driver and needs no URL/config mutation outside this process.
    url = make_url(database_url)
    if url.drivername == "mysql":
        url = url.set(drivername="mysql+pymysql")
    options: dict = {"pool_pre_ping": True, "future": True}
    if database_url.startswith("sqlite"):
        # Test databases may be used across TestClient worker threads.
        options["connect_args"] = {"check_same_thread": False}
    elif url.drivername == "mysql+pymysql":
        query = dict(url.query)
        ssl_value = query.pop("ssl", None)
        connect_args: dict = {"connect_timeout": 15}
        if ssl_value is not None:
            try:
                supplied = json.loads(ssl_value) if isinstance(ssl_value, str) else ssl_value
            except ValueError:
                supplied = {}
            context = ssl.create_default_context()
            if isinstance(supplied, dict) and supplied.get("ca"):
                ca = supplied["ca"]
                context.load_verify_locations(cadata="\n".join(ca) if isinstance(ca, list) else ca)
            # Keep certificate/hostname validation enabled. No TLS-error retry
            # disables verification or exposes the credential-bearing URL.
            connect_args["ssl"] = context
        options["connect_args"] = connect_args
        url = url.set(query=query)
    return create_engine(url, **options)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    """Create hosted tables explicitly (used by isolated tests or a migration runner)."""
    Base.metadata.create_all(bind=engine)


class HostedUser(Base):
    __tablename__ = "jh_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    open_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    # This is an application CSRF secret, never an OAuth access token.
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    profile: Mapped[Optional["HostedProfile"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class HostedProfile(Base):
    __tablename__ = "jh_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("jh_users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    # Keep these legacy preference names and types compatible with src.scorer.
    job_profiles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    role_tracks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    experience_level: Mapped[str] = mapped_column(String(32), nullable=False, default="junior")
    preferred_tech: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    preferred_locations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    remote_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hybrid_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    alert_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Drafts retain only validated preference values and the six-step position.
    draft: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    draft_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user: Mapped[HostedUser] = relationship(back_populates="profile")


class HostedJob(Base):
    """A public, source-owned job listing. It intentionally has no user ownership column."""

    __tablename__ = "jh_jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_jh_jobs_source_source_id"),
        Index("ix_jh_jobs_visible_source", "hidden", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    date_posted: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    salary_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    salary_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    salary_period: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hybrid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    company_size: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    company_founded: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    company_website: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    company_perks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # These baseline values are retained for source diagnostics. User-specific
    # score fields are calculated at read time and never written here.
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    learning_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    worklife_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tech_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    company_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class HostedSavedJob(Base):
    __tablename__ = "jh_saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_jh_saved_jobs_user_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("jh_users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jh_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class HostedApplication(Base):
    __tablename__ = "jh_applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_jh_applications_user_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("jh_users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jh_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="saved")
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class HostedFetchRun(Base):
    """Durable refresh state. ``active_key`` permits at most one active run."""

    __tablename__ = "jh_fetch_runs"
    __table_args__ = (Index("ix_jh_fetch_runs_status_started", "status", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The literal value "active" is unique while queued/running, then cleared.
    active_key: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jh_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_status: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class HostedSourceHealth(Base):
    __tablename__ = "jh_source_health"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class HostedSchedule(Base):
    """A future schedule binding; no route in this module registers one."""

    __tablename__ = "jh_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    task_uid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

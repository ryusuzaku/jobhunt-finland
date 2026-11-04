"""Hosted data access, personalized presentation, and durable refresh work."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import Select, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.job_profiles import JOB_PROFILES, keep_job
from src.scorer import score_job

from .models import (
    HostedApplication,
    HostedFetchRun,
    HostedJob,
    HostedSavedJob,
    HostedSourceHealth,
    utcnow,
)

PAGE_SIZE = 24
APPLIED_HIDING_STATUSES = {"applied", "interview", "offer", "rejected", "withdrawn", "ghosted"}


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return list(dict.fromkeys(piece.strip().lower() for piece in value.split(",") if piece.strip()))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


def _safe_http_url(value: str | None) -> str:
    """Only expose third-party web URLs that a browser can safely navigate."""
    if not value:
        return ""
    parsed = urlparse(value.strip())
    return value.strip() if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    except (OverflowError, OSError, ValueError):
        return 0.0


def _profile_matches(job: HostedJob, prefs: dict[str, Any]) -> list[str]:
    """Explain only concrete signals used in the personalized presentation."""
    text = f"{job.title} {job.description}".lower()
    reasons: list[str] = []
    selected = prefs.get("job_profiles") or prefs.get("role_tracks") or []
    for key in selected:
        info = JOB_PROFILES.get(key)
        if not info:
            continue
        if any(keyword.replace("*", "") and keyword.replace("*", "") in text for keyword in info["title_keywords"]):
            reasons.append(f"Matches your selected field: {info['label']}")
            break
    technologies = [tech for tech in prefs.get("preferred_tech", []) if tech and tech.lower() in text]
    if technologies:
        reasons.append("Matches your skills: " + ", ".join(technologies[:3]))
    location = (job.location or "").lower()
    if any(loc and loc.lower() in location for loc in prefs.get("preferred_locations", [])):
        reasons.append("Matches a preferred location")
    if job.remote and prefs.get("remote_ok"):
        reasons.append("Remote work is available")
    elif job.hybrid and prefs.get("hybrid_ok"):
        reasons.append("Hybrid work is available")
    return reasons


def _personalized_job(
    job: HostedJob,
    prefs: dict[str, Any],
    saved: bool,
    application: HostedApplication | None,
) -> dict[str, Any]:
    scores = score_job(
        title=job.title or "",
        description=job.description or "",
        location=job.location or "",
        prefs=prefs,
        remote=bool(job.remote),
        hybrid=bool(job.hybrid),
        company_size=job.company_size,
        company_founded=job.company_founded,
        company_perks=job.company_perks or [],
    )
    reasons = _profile_matches(job, prefs)
    if scores["learning_score"] and not any("growth" in item.lower() for item in reasons):
        reasons.append("Includes learning or growth signals")
    if scores["company_score"] and len(reasons) < 4:
        reasons.append("Includes positive company signals")
    if not reasons:
        reasons.append("Ranked using your saved preferences")
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "url": _safe_http_url(job.url),
        "date_posted": _iso(job.date_posted),
        "last_seen_at": _iso(job.updated_at),
        "verification_stale": _timestamp(job.updated_at) < (utcnow() - timedelta(days=7)).timestamp(),
        "remote": bool(job.remote),
        "hybrid": bool(job.hybrid),
        "salary_text": job.salary_text,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "source": job.source,
        "score": scores["score"],
        "learning_score": scores["learning_score"],
        "worklife_score": scores["worklife_score"],
        "tech_score": scores["tech_score"],
        "company_score": scores["company_score"],
        "match_reasons": reasons,
        "saved": saved,
        "application": application_to_dict(application) if application else None,
    }


def application_to_dict(application: HostedApplication | None) -> dict[str, Any] | None:
    if application is None:
        return None
    return {
        "id": application.id,
        "status": application.status,
        "applied_at": _iso(application.applied_at),
        "closing_date": _iso(application.closing_date),
        "notes": application.notes or "",
        "outcome": application.outcome or "",
        "updated_at": _iso(application.updated_at),
    }


def _job_state_maps(db: Session, user_id: int, job_ids: list[int]) -> tuple[set[int], dict[int, HostedApplication]]:
    if not job_ids:
        return set(), {}
    saved = set(
        db.scalars(
            select(HostedSavedJob.job_id).where(
                HostedSavedJob.user_id == user_id, HostedSavedJob.job_id.in_(job_ids)
            )
        ).all()
    )
    apps = db.scalars(
        select(HostedApplication).where(
            HostedApplication.user_id == user_id, HostedApplication.job_id.in_(job_ids)
        )
    ).all()
    return saved, {item.job_id: item for item in apps}


def list_jobs(
    db: Session,
    *,
    user_id: int,
    prefs: dict[str, Any],
    page: int = 1,
    q: str = "",
    location: str = "",
    work: str = "",
    source: str = "",
    min_score: float = 0.0,
    sort: str = "match",
    show_applied: bool = False,
    saved_only: bool = False,
) -> dict[str, Any]:
    """Filter, personalize, rank, then paginate public listings for one user.

    Scoring cannot be safely reused from another person, so it intentionally
    happens before min-score filtering and pagination.
    """
    statement: Select = select(HostedJob).where(HostedJob.hidden.is_(False))
    if saved_only:
        saved_ids = select(HostedSavedJob.job_id).where(HostedSavedJob.user_id == user_id)
        statement = statement.where(HostedJob.id.in_(saved_ids))
    else:
        # Stop recommending listings no source has seen recently. Keep the row,
        # bookmarks and application notes available instead of cascading deletion.
        statement = statement.where(HostedJob.updated_at >= utcnow() - timedelta(days=7))
    source_values = _csv(source)
    if source_values:
        statement = statement.where(HostedJob.source.in_(source_values))
    # SQL prefilters are safe because they do not depend on another user's state.
    if q:
        needle = q.strip().lower()
        if needle:
            statement = statement.where(
                (HostedJob.title.ilike(f"%{needle}%"))
                | (HostedJob.company.ilike(f"%{needle}%"))
                | (HostedJob.location.ilike(f"%{needle}%"))
            )
    locations = _csv(location)
    if locations and "finland" not in locations:
        statement = statement.where(or_(*(HostedJob.location.ilike(f"%{value}%") for value in locations)))
    work_values = set(_csv(work))
    if work_values:
        if work_values == {"remote"}:
            statement = statement.where(HostedJob.remote.is_(True))
        elif work_values == {"hybrid"}:
            statement = statement.where(HostedJob.hybrid.is_(True))
        elif work_values.intersection({"remote", "hybrid"}):
            statement = statement.where(HostedJob.remote.is_(True) | HostedJob.hybrid.is_(True))

    rows = db.scalars(statement).all()
    saved_ids, applications = _job_state_maps(db, user_id, [job.id for job in rows])
    presented: list[dict[str, Any]] = []
    for job in rows:
        if not saved_only:
            fields = prefs.get("job_profiles") or prefs.get("role_tracks") or ["software", "frontend", "data", "devops", "mobile", "qa", "security"]
            if not keep_job(job.title, job.description, fields):
                continue
            preferred = locations or [value.lower() for value in prefs.get("preferred_locations", [])]
            place = (job.location or "").lower()
            fi_cities = ("helsinki", "espoo", "vantaa", "tampere", "turku", "oulu", "finland", "suomi", "jyväskylä", "kuopio", "lahti", "vaasa", "pori", "joensuu", "seinäjoki", "rovaniemi", "lappeenranta", "salo", "kouvola", "porvoo", "hämeenlinna", "mikkeli", "kotka")
            nation_match = "finland" in preferred and (job.source in {"duunitori", "thehub", "englishjobs", "jobly", "academicwork"} or any(city in place for city in fi_cities))
            remote_match = bool(job.remote and prefs.get("remote_ok"))
            if preferred and not (nation_match or remote_match or any(value in place for value in preferred)):
                continue
        application = applications.get(job.id)
        if not show_applied and application and application.status in APPLIED_HIDING_STATUSES:
            continue
        item = _personalized_job(job, prefs, job.id in saved_ids, application)
        if item["score"] < min_score:
            continue
        presented.append(item)

    if sort == "newest":
        presented.sort(key=lambda item: (_timestamp_from_iso(item["date_posted"]), item["score"]), reverse=True)
    elif sort == "company":
        presented.sort(key=lambda item: (item["company"].lower(), -item["score"], item["title"].lower()))
    else:
        sort = "match"
        presented.sort(key=lambda item: (-item["score"], -_timestamp_from_iso(item["date_posted"]), item["title"].lower()))

    total = len(presented)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(int(page or 1), page_count))
    start = (page - 1) * PAGE_SIZE
    return {
        "jobs": presented[start : start + PAGE_SIZE],
        "total": total,
        "page": page,
        "page_count": page_count,
        "filters": {
            "q": q,
            "location": location,
            "work": work,
            "source": source,
            "min_score": min_score,
            "sort": sort,
            "show_applied": show_applied,
        },
    }


def _timestamp_from_iso(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return _timestamp(parsed)


def get_presented_job(db: Session, user_id: int, prefs: dict[str, Any], job_id: int) -> dict[str, Any] | None:
    job = db.get(HostedJob, job_id)
    if job is None or job.hidden:
        return None
    saved, apps = _job_state_maps(db, user_id, [job_id])
    return _personalized_job(job, prefs, job_id in saved, apps.get(job_id))


def list_applications(db: Session, user_id: int, prefs: dict[str, Any]) -> list[dict[str, Any]]:
    applications = db.scalars(
        select(HostedApplication)
        .where(HostedApplication.user_id == user_id)
        .order_by(HostedApplication.applied_at.desc(), HostedApplication.updated_at.desc())
    ).all()
    jobs = {job.id: job for job in db.scalars(select(HostedJob).where(HostedJob.id.in_([a.job_id for a in applications]))).all()} if applications else {}
    saved, _ = _job_state_maps(db, user_id, list(jobs))
    result = []
    for application in applications:
        job = jobs.get(application.job_id)
        if job is None:
            continue
        record = application_to_dict(application) or {}
        record["job"] = _personalized_job(job, prefs, job.id in saved, application)
        result.append(record)
    return result


def source_health(db: Session) -> dict[str, dict[str, Any]]:
    rows = db.scalars(select(HostedSourceHealth).order_by(HostedSourceHealth.source)).all()
    return {
        row.source: {
            "status": row.status,
            "count": row.count,
            "error": row.error,
            "updated_at": _iso(row.updated_at),
            **(row.details or {}),
        }
        for row in rows
    }


def fetch_run_to_dict(run: HostedFetchRun | None) -> dict[str, Any]:
    if run is None:
        return {"status": "idle", "ok": True, "started_at": None, "finished_at": None, "sources": {}}
    return {
        "id": run.id,
        "status": run.status,
        "ok": run.status == "success",
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "error": run.error,
        "sources": run.source_status or {},
        **(run.result or {}),
    }


def _aware(value: datetime | None) -> datetime | None:
    if value and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def acquire_refresh(db: Session, triggered_by_user_id: int | None = None) -> tuple[HostedFetchRun, bool]:
    """Create one active run or join it, persisting state before work begins."""
    active = db.scalar(select(HostedFetchRun).where(HostedFetchRun.active_key == "active"))
    if active is not None:
        started = _aware(active.started_at or active.created_at)
        # A process can be killed after persisting a run. Do not report it as
        # forever running; source work is bounded and stale after 20 minutes.
        if started and started < utcnow() - timedelta(minutes=20):
            active.status = "error"
            active.error = "Refresh did not finish before its bounded lease expired"
            active.finished_at = utcnow()
            active.active_key = None
            db.commit()
        else:
            return active, False
    run = HostedFetchRun(active_key="active", status="queued", triggered_by_user_id=triggered_by_user_id)
    db.add(run)
    try:
        db.commit()
        db.refresh(run)
        return run, True
    except IntegrityError:
        # A second web worker inserted the active marker concurrently.
        db.rollback()
        existing = db.scalar(select(HostedFetchRun).where(HostedFetchRun.active_key == "active"))
        if existing is None:
            raise
        return existing, False


async def execute_refresh(run_id: int, session_factory: sessionmaker[Session]) -> dict[str, Any]:
    """Fetch global source data and await persistence; appropriate for cron callbacks."""
    db = session_factory()
    try:
        run = db.get(HostedFetchRun, run_id)
        if run is None:
            raise ValueError("Refresh run no longer exists")
        if run.status == "success":
            return fetch_run_to_dict(run)
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        db.commit()
    finally:
        db.close()

    try:
        from .source_fetch import fetch_hosted_sources
        raw_jobs, statuses = await fetch_hosted_sources(session_factory, run_id)
        return await asyncio.to_thread(_persist_refresh, run_id, raw_jobs, statuses, session_factory)
    except Exception as exc:
        return await asyncio.to_thread(_mark_refresh_error, run_id, type(exc).__name__, session_factory)


def _persist_refresh(
    run_id: int,
    raw_jobs: Iterable[dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    session_factory: sessionmaker[Session],
) -> dict[str, Any]:
    db = session_factory()
    try:
        run = db.get(HostedFetchRun, run_id)
        if run is None:
            raise ValueError("Refresh run no longer exists")
        new_count = 0
        updated_count = 0
        unique = {}
        for raw in raw_jobs:
            source = str(raw.get("source") or "").strip().lower()[:64]
            identifier = str(raw.get("source_id") or "").strip()[:512]
            if source and identifier:
                unique[(source, identifier)] = raw
        rows = db.scalars(select(HostedJob).where(HostedJob.source.in_({key[0] for key in unique}))).all() if unique else []
        existing_by_key = {(job.source, job.source_id): job for job in rows}
        mysql_batches = []
        is_mysql = db.get_bind().dialect.name == "mysql"
        for (source, source_id), raw in unique.items():
            existing = existing_by_key.get((source, source_id))
            if existing is not None and statuses.get(source, {}).get("status") == "cached":
                continue
            valid_url = _safe_http_url(raw.get("url"))
            neutral_scores = score_job(
                title=str(raw.get("title") or ""),
                description=str(raw.get("description") or ""),
                location=str(raw.get("location") or ""),
                prefs={},
                remote=bool(raw.get("remote")),
                hybrid=bool(raw.get("hybrid")),
                company_size=raw.get("company_size"),
                company_founded=raw.get("company_founded"),
                company_perks=raw.get("company_perks") or [],
            )
            values = {
                "title": str(raw.get("title") or "")[:500],
                "company": str(raw.get("company") or "")[:255],
                "location": str(raw.get("location") or "")[:255],
                "description": str(raw.get("description") or ""),
                "url": valid_url,
                "date_posted": raw.get("date_posted"),
                "salary_text": (str(raw.get("salary_text"))[:500] if raw.get("salary_text") else None),
                "salary_min": raw.get("salary_min"),
                "salary_max": raw.get("salary_max"),
                "salary_currency": (str(raw.get("salary_currency"))[:16] if raw.get("salary_currency") else None),
                "salary_period": (str(raw.get("salary_period"))[:32] if raw.get("salary_period") else None),
                "remote": bool(raw.get("remote")),
                "hybrid": bool(raw.get("hybrid")),
                "company_size": (str(raw.get("company_size"))[:64] if raw.get("company_size") else None),
                "company_founded": (str(raw.get("company_founded"))[:32] if raw.get("company_founded") else None),
                "company_website": _safe_http_url(raw.get("company_website")) or None,
                "company_perks": list(raw.get("company_perks") or []),
                **neutral_scores,
            }
            if is_mysql:
                mysql_batches.append({"source":source, "source_id":source_id, **values, "updated_at":utcnow()})
                if existing is None:
                    new_count += 1
                else:
                    updated_count += 1
                continue
            if existing is None:
                db.add(HostedJob(source=source, source_id=source_id, **values))
                new_count += 1
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
                if statuses.get(source, {}).get("status") == "fresh":
                    existing.updated_at = utcnow()
                updated_count += 1

        if mysql_batches:
            from sqlalchemy.dialects.mysql import insert as mysql_insert
            for start in range(0, len(mysql_batches), 50):
                statement = mysql_insert(HostedJob).values(mysql_batches[start:start + 50])
                columns = [key for key in mysql_batches[0] if key not in {"source", "source_id"}]
                db.execute(statement.on_duplicate_key_update(**{key: getattr(statement.inserted, key) for key in columns}))

        for name, state in statuses.items():
            record = db.get(HostedSourceHealth, name)
            if record is None:
                record = HostedSourceHealth(source=name)
                db.add(record)
            record.status = str(state.get("status") or "unknown")[:32]
            record.count = int(state.get("count") or 0)
            record.error = (str(state.get("error"))[:255] if state.get("error") else None)
            record.details = {key: value for key, value in state.items() if key not in {"status", "count", "error"}}
            record.updated_at = utcnow()

        completed_source_states = {"fresh", "cached", "empty"}
        any_source_completed = any(
            str(state.get("status") or "") in completed_source_states for state in statuses.values()
        )
        # An individual error (including Shine's explicit layout failure) is
        # useful source health, not a failed whole run. If no source completed,
        # however, returning success would misrepresent the refresh result.
        run.status = "success" if any_source_completed else "error"
        run.source_status = statuses
        run.result = {"new_jobs": new_count, "updated_jobs": updated_count}
        run.error = None if any_source_completed else "No source completed successfully"
        run.finished_at = utcnow()
        run.active_key = None
        db.commit()
        db.refresh(run)
        return fetch_run_to_dict(run)
    except Exception as exc:
        db.rollback()
        return _mark_refresh_error(run_id, type(exc).__name__, session_factory)
    finally:
        db.close()


def _mark_refresh_error(run_id: int, error: str, session_factory: sessionmaker[Session]) -> dict[str, Any]:
    db = session_factory()
    try:
        run = db.get(HostedFetchRun, run_id)
        if run is None:
            return {"status": "error", "ok": False, "error": "Refresh run no longer exists"}
        run.status = "error"
        run.error = error[:255]
        run.finished_at = utcnow()
        run.active_key = None
        db.commit()
        db.refresh(run)
        return fetch_run_to_dict(run)
    finally:
        db.close()

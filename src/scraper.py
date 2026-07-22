import logging
import re
import unicodedata
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from src.cache import CachedAsyncClient, JobSnapshotCache
from src.config import settings
from src.models import Job
from src.scorer import score_job
from src.sources import (
    DuunitoriSource,
    TheHubSource,
    EnglishJobsSource,
    JoblySource,
    AcademicWorkSource,
    LinkedInSource,
    RemoteOKSource,
    RemotiveSource,
    WorkingNomadsSource,
    WeWorkRemotelySource,
    HasjobSource,
    ShineSource,
    InternshalaSource,
    CompanyCareersSource,
)

logger = logging.getLogger(__name__)

SOURCES = [
    DuunitoriSource(),
    TheHubSource(),
    EnglishJobsSource(),
    JoblySource(),
    AcademicWorkSource(),
    LinkedInSource(),
    RemoteOKSource(),
    RemotiveSource(),
    WorkingNomadsSource(),
    WeWorkRemotelySource(),
    HasjobSource(),
    ShineSource(),
    InternshalaSource(),
    CompanyCareersSource(),
]

snapshot_cache = JobSnapshotCache()


async def fetch_all_jobs() -> tuple[list[dict], dict[str, set[str]]]:
    """Fetch raw job postings from all configured sources.

    Uses a cached HTTP client to avoid hammering sources on every refresh, and
    falls back to the previous snapshot if a source fails or returns empty.

    Returns:
        - List of normalized job dicts from all sources.
        - Dict mapping source name -> set of fetched source_ids, used later to
          prune stale DB rows for sources that succeeded this run.
    """
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    fetched_sources: dict[str, set[str]] = {}
    async with CachedAsyncClient(
        timeout=settings.request_timeout,
        limits=limits,
        ttl=getattr(settings, "cache_ttl_seconds", 1800),
        follow_redirects=True,
    ) as client:
        all_raw: list[dict] = []
        for source in SOURCES:
            source_name = source.name
            previous = snapshot_cache.get(source_name)
            source_ids: set[str] = set()
            try:
                raw = await source.fetch(client)
                normalized = []
                for item in raw:
                    try:
                        norm = source.normalize(item)
                        if norm:
                            normalized.append(norm)
                    except Exception as exc:
                        logger.warning("Normalization error for %s: %s", source_name, exc)

                if not normalized and previous:
                    logger.info(
                        "%s returned no jobs; falling back to %d cached snapshot jobs",
                        source_name,
                        len(previous),
                    )
                    normalized = previous
                else:
                    new, removed = snapshot_cache.diff(source_name, normalized)
                    if new or removed:
                        logger.info(
                            "%s snapshot diff: +%d new, -%d removed",
                            source_name,
                            len(new),
                            len(removed),
                        )
                    # Only prune this source if the fetch itself succeeded.
                    source_ids = {j.get("source_id") for j in normalized if j.get("source_id")}

                snapshot_cache.update(source_name, normalized)
                all_raw.extend(normalized)
                logger.info("%s contributed %d jobs", source_name, len(normalized))
                if source_ids:
                    fetched_sources[source_name] = source_ids
            except Exception as exc:
                logger.error("Source %s failed: %s", source_name, exc)
                if previous:
                    logger.info(
                        "%s failed; using %d cached snapshot jobs",
                        source_name,
                        len(previous),
                    )
                    all_raw.extend(previous)
        return all_raw, fetched_sources


def save_jobs(db: Session, normalized_jobs: list[dict], prefs: dict | None = None) -> tuple[int, int]:
    """Save or update jobs in the database and return (new_count, updated_count)."""
    if prefs is None:
        prefs = {}

    new_count = 0
    updated_count = 0

    for job in normalized_jobs:
        source = job.get("source")
        source_id = job.get("source_id")
        if not source or not source_id:
            continue

        scores = score_job(
            title=job.get("title", ""),
            description=job.get("description", ""),
            location=job.get("location", ""),
            prefs=prefs,
            remote=job.get("remote", False),
            hybrid=job.get("hybrid", False),
            company_size=job.get("company_size"),
            company_founded=job.get("company_founded"),
            company_perks=job.get("company_perks") or [],
        )

        existing = db.query(Job).filter(Job.source == source, Job.source_id == source_id).first()
        if existing:
            existing.title = job.get("title", "")
            existing.company = job.get("company", "")
            existing.location = job.get("location", "")
            existing.description = job.get("description", "")
            existing.url = job.get("url", "")
            existing.date_posted = job.get("date_posted")
            existing.salary_text = job.get("salary_text")
            existing.salary_min = job.get("salary_min")
            existing.salary_max = job.get("salary_max")
            existing.salary_currency = job.get("salary_currency")
            existing.salary_period = job.get("salary_period")
            existing.remote = job.get("remote", False)
            existing.hybrid = job.get("hybrid", False)
            existing.company_size = job.get("company_size")
            existing.company_founded = job.get("company_founded")
            existing.company_website = job.get("company_website")
            existing.company_perks = job.get("company_perks") or []
            existing.score = scores["score"]
            existing.learning_score = scores["learning_score"]
            existing.worklife_score = scores["worklife_score"]
            existing.tech_score = scores["tech_score"]
            existing.company_score = scores["company_score"]
            existing.updated_at = datetime.utcnow()
            existing.is_new = False
            updated_count += 1
        else:
            new_job = Job(
                source=source,
                source_id=source_id,
                title=job.get("title", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                description=job.get("description", ""),
                url=job.get("url", ""),
                date_posted=job.get("date_posted"),
                salary_text=job.get("salary_text"),
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                salary_currency=job.get("salary_currency"),
                salary_period=job.get("salary_period"),
                remote=job.get("remote", False),
                hybrid=job.get("hybrid", False),
                company_size=job.get("company_size"),
                company_founded=job.get("company_founded"),
                company_website=job.get("company_website"),
                company_perks=job.get("company_perks") or [],
                score=scores["score"],
                learning_score=scores["learning_score"],
                worklife_score=scores["worklife_score"],
                tech_score=scores["tech_score"],
                company_score=scores["company_score"],
            )
            db.add(new_job)
            new_count += 1

    db.commit()
    return new_count, updated_count


# Sources whose URLs point directly at the employer are preferred when merging
# duplicate postings of the same role.
_SOURCE_PRIORITY = {
    "companycareers": 0,
    "duunitori": 1,
    "thehub": 2,
    "jobly": 3,
    "englishjobs": 4,
    "academicwork": 5,
    "linkedin": 6,
}

_COMPANY_SUFFIXES = re.compile(
    r"\b(oy|oyj|ab|ltd|limited|inc|llc|pvt|gmbh|plc|corp|corporation|co)\b"
)


def _norm_text(text: str) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _norm_company(company: str) -> str:
    return _COMPANY_SUFFIXES.sub("", _norm_text(company)).strip()


def dedupe_jobs(db: Session) -> int:
    """Delete cross-source duplicates of the same role at the same company.

    Jobs are grouped by normalized (title, company). Several rows from the
    SAME source are treated as distinct openings (e.g. one title posted for
    multiple offices) and are kept. When the same role appears in MULTIPLE
    sources, only the best row survives: tracked application > direct-
    employer source > newest posting > highest score.
    """
    jobs = db.query(Job).filter(Job.hidden == False).all()
    groups: dict[tuple[str, str], list[Job]] = {}
    for job in jobs:
        title_key = _norm_text(job.title or "")
        company_key = _norm_company(job.company or "")
        if not title_key or not company_key:
            continue
        groups.setdefault((title_key, company_key), []).append(job)

    _EPOCH = datetime(1970, 1, 1)

    def _posted_ts(j: Job) -> float:
        # datetime.timestamp() raises OSError 22 on Windows for pre-1970
        # dates (some sources yield broken dates); subtract instead.
        if not j.date_posted:
            return 0.0
        try:
            return max(0.0, (j.date_posted - _EPOCH).total_seconds())
        except (OverflowError, OSError, TypeError):
            return 0.0

    def _rank(j: Job):
        has_app = 0 if j.application else 1
        priority = _SOURCE_PRIORITY.get(j.source, 9)
        return (has_app, priority, -_posted_ts(j), -(j.score or 0))

    removed = 0
    for group in groups.values():
        if len(group) < 2:
            continue

        # Keep the best row per source; within-source duplicates are
        # considered distinct openings and are left alone.
        best_per_source: dict[str, Job] = {}
        for job in group:
            current = best_per_source.get(job.source)
            if current is None or _rank(job) < _rank(current):
                best_per_source[job.source] = job
        candidates = list(best_per_source.values())
        if len(candidates) < 2:
            continue

        candidates.sort(key=_rank)
        keeper = candidates[0]
        keeper.is_new = any(j.is_new for j in group)
        for dup in candidates[1:]:
            logger.info(
                "Dedup: removing '%s' at %s (%s), keeping %s",
                dup.title, dup.company, dup.source, keeper.source,
            )
            db.delete(dup)
            removed += 1

    if removed:
        db.commit()
    logger.info("Dedup removed %d duplicate jobs", removed)
    return removed


def prune_stale_jobs(
    db: Session,
    fetched_sources: dict[str, set[str]],
    max_age_days: int = 7,
) -> int:
    """Delete DB rows for sources that were successfully fetched but are no longer present.

    This keeps the dashboard free of removed or garbled listings that sources
    have dropped.  Sources that failed (and fell back to the snapshot) are not
    pruned so we don't lose jobs during a temporary outage.
    """
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    removed = 0
    for source, source_ids in fetched_sources.items():
        if not source_ids:
            continue
        stale = (
            db.query(Job)
            .filter(
                Job.source == source,
                Job.source_id.notin_(source_ids),
                Job.updated_at < cutoff,
            )
            .all()
        )
        for job in stale:
            db.delete(job)
            removed += 1
    db.commit()
    logger.info("Pruned %d stale jobs", removed)
    return removed

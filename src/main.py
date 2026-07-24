import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlencode
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings
from src.models import Base, engine, get_db, Job, Application
from src.scorer import score_job
from src.scraper import fetch_all_jobs, save_jobs, prune_stale_jobs, dedupe_jobs
from src.alerts import send_console_alerts, send_email_alerts, send_discord_alerts, send_slack_alerts
from src.preferences import get_preferences, set_preferences
from src.job_profiles import JOB_PROFILES, PROFILE_GROUPS

# Scraped job titles may contain characters the Windows console encoding
# (e.g. cp932) cannot represent; reconfigure std streams so logging/prints
# never crash the fetch loop with UnicodeEncodeError / OSError 22.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Application lifecycle statuses
APPLICATION_STATUSES = [
    "saved",
    "applied",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "ghosted",
]

# Create tables
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="src/templates")


async def fetch_and_process():
    """Fetch jobs, score them, save to DB, and send alerts."""
    db = next(get_db())
    try:
        prefs = get_preferences(db)
        logger.info("Starting job fetch...")
        profiles = prefs.get("job_profiles") or prefs.get("role_tracks") or []
        raw, fetched_sources = await fetch_all_jobs(profiles=profiles)
        new, updated = save_jobs(db, raw, prefs)
        logger.info("Saved %d new jobs, updated %d existing jobs", new, updated)
        removed_dupes = dedupe_jobs(db)
        if removed_dupes:
            logger.info("Removed %d duplicate jobs", removed_dupes)
        prune_stale_jobs(db, fetched_sources)
        alerted = send_console_alerts(db)
        if settings.smtp_host:
            send_email_alerts(db, alerted)
        if settings.discord_webhook_url:
            send_discord_alerts(db, alerted)
        if settings.slack_webhook_url:
            send_slack_alerts(db, alerted)
    except Exception as exc:
        logger.error("Job fetch failed: %s", exc)
    finally:
        db.close()


scheduler = AsyncIOScheduler()
scheduler.add_job(fetch_and_process, "interval", minutes=60, id="fetch_jobs", replace_existing=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    _migrate_unhide_tracked_jobs()
    logger.info("Scheduler started. Fetching jobs on startup...")
    await fetch_and_process()
    yield
    scheduler.shutdown()


def _migrate_unhide_tracked_jobs() -> None:
    """One-time migration for the old track-to-hide behavior.

    Jobs that were hidden because they were tracked get unhidden — they are
    now shown with a status badge (saved) or filtered out via the tracked
    filter (applied+). Manual hides (no application row) stay hidden.
    """
    db = next(get_db())
    try:
        tracked_ids = select(Application.job_id)
        updated = (
            db.query(Job)
            .filter(Job.hidden == True, Job.id.in_(tracked_ids))
            .update({Job.hidden: False}, synchronize_session=False)
        )
        if updated:
            db.commit()
            logger.info("Migration: unhid %d previously tracked jobs", updated)
    except Exception as exc:
        logger.warning("Tracked-job migration failed: %s", exc)
        db.rollback()
    finally:
        db.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/static"), name="static")


def _allowed_location_clause():
    """SQLAlchemy filter: job location must contain one of the allowed cities."""
    return or_(
        *[
            Job.location.ilike(f"%{loc}%")
            for loc in settings.allowed_dashboard_locations
        ]
    )


def _csv(value: str | None) -> list[str]:
    """Parse a comma-separated query param into a clean list."""
    if not value:
        return []
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def _sort_order(sort: str) -> list:
    """ORDER BY clauses for the dashboard sort param."""
    if sort == "newest":
        return [Job.date_posted.desc().nullslast(), Job.created_at.desc()]
    if sort == "company":
        return [Job.company.asc(), Job.score.desc()]
    # "match" (default): best score first, newest as tiebreak.
    return [Job.score.desc(), Job.date_posted.desc().nullslast()]


def _jobs_context(
    request: Request,
    db: Session,
    page: int = 1,
    bengaluru_only: bool = False,
    q: str = "",
    min_score: float = 0.0,
    sources: str = "",
    locations: str = "",
    work: str = "",
    sort: str = "match",
    tracked: str = "",
):
    """Shared dashboard context with server-side filtering.

    Filters arrive as query params so filtered views are shareable URLs
    and pagination stays consistent (no client-side-only filtering).
    """
    page_size = settings.dashboard_page_size
    active_sources = _csv(sources)
    active_locations = _csv(locations)
    active_work = _csv(work)

    query = db.query(Job).options(joinedload(Job.application)).filter(Job.hidden == False)
    if bengaluru_only:
        query = query.filter(
            or_(Job.location.ilike("%bengaluru%"), Job.location.ilike("%bangalore%"))
        )
    else:
        query = query.filter(_allowed_location_clause())

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Job.title.ilike(like),
                Job.company.ilike(like),
                Job.location.ilike(like),
            )
        )
    if min_score:
        query = query.filter(Job.score >= min_score)
    if active_sources:
        query = query.filter(Job.source.in_(active_sources))
    if active_locations:
        query = query.filter(
            or_(*[Job.location.ilike(f"%{loc}%") for loc in active_locations])
        )
    if active_work:
        work_conds = []
        if "remote" in active_work:
            work_conds.append(Job.remote == True)
        if "hybrid" in active_work:
            work_conds.append(Job.hybrid == True)
        if work_conds:
            query = query.filter(or_(*work_conds))

    # Tracked jobs: "saved" stays visible (with a badge); applied-or-later
    # is filtered out of the feed unless ?tracked=all.
    if tracked != "all":
        query = query.outerjoin(Job.application).filter(
            or_(Application.id == None, Application.status == "saved")
        )

    total_jobs = query.count()
    new_count = query.filter(Job.is_new == True).count()
    total_pages = max(1, (total_jobs + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    order = _sort_order(sort)
    jobs = (
        query.order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    scores = [j.score for j in jobs]
    avg_score = round(sum(scores) / len(scores), 0) if scores else 0
    prefs = get_preferences(db)

    # Distinct sources in the whole DB so filters show every source,
    # not just the ones that happen to be in the top results.
    all_sources = sorted(
        {row[0] for row in db.query(Job.source).distinct() if row[0]}
    )

    base_qs = urlencode(
        {
            "q": q,
            "min_score": int(min_score),
            "sources": ",".join(active_sources),
            "locations": ",".join(active_locations),
            "work": ",".join(active_work),
            "sort": sort,
            "tracked": tracked,
        }
    )

    return {
        "request": request,
        "jobs": jobs,
        "avg_score": avg_score,
        "new_count": new_count,
        "settings": settings,
        "prefs": prefs,
        "sources": all_sources,
        "locations": settings.allowed_dashboard_locations,
        "page": page,
        "total_pages": total_pages,
        "total_jobs": total_jobs,
        "q": q,
        "min_score": int(min_score),
        "active_sources": active_sources,
        "active_locations": active_locations,
        "active_work": active_work,
        "sort": sort,
        "tracked": tracked,
        "base_qs": base_qs,
        "base_qs_nosort": urlencode(
            {
                "q": q,
                "min_score": int(min_score),
                "sources": ",".join(active_sources),
                "locations": ",".join(active_locations),
                "work": ",".join(active_work),
                "tracked": tracked,
            }
        ),
    }


@app.get("/offline", response_class=HTMLResponse)
def offline_page(request: Request):
    """Fallback page served by the service worker when the network is down."""
    return templates.TemplateResponse(
        request, "offline.html", {"request": request, "settings": settings}
    )


@app.get("/api/locations")
def api_locations(db: Session = Depends(get_db)):
    """Return allowed locations that actually appear in visible jobs."""
    rows = (
        db.query(Job.location)
        .filter(Job.hidden == False, _allowed_location_clause())
        .distinct()
        .all()
    )
    found = set()
    for row in rows:
        loc = (row[0] or "").lower()
        for allowed in settings.allowed_dashboard_locations:
            if allowed in loc:
                found.add(allowed)
    return sorted(found)


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    page: int = 1,
    q: str = "",
    min_score: float = 0.0,
    sources: str = "",
    locations: str = "",
    work: str = "",
    sort: str = "match",
    tracked: str = "",
    db: Session = Depends(get_db),
):
    # First visit: guide the user through the onboarding questionnaire.
    prefs = get_preferences(db)
    if not prefs.get("onboarding_completed"):
        return RedirectResponse(url="/onboarding", status_code=303)
    return templates.TemplateResponse(
        request,
        "index.html",
        _jobs_context(
            request, db, page=page, q=q, min_score=min_score,
            sources=sources, locations=locations, work=work,
            sort=sort, tracked=tracked,
        ),
    )


@app.get("/bengaluru", response_class=HTMLResponse)
def bengaluru(
    request: Request,
    page: int = 1,
    q: str = "",
    min_score: float = 0.0,
    sources: str = "",
    work: str = "",
    sort: str = "match",
    tracked: str = "",
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "bengaluru.html",
        _jobs_context(
            request, db, page=page, bengaluru_only=True, q=q,
            min_score=min_score, sources=sources, work=work,
            sort=sort, tracked=tracked,
        ),
    )


@app.get("/preferences", response_class=HTMLResponse)
def preferences_page(request: Request, db: Session = Depends(get_db)):
    prefs = get_preferences(db)
    return templates.TemplateResponse(
        request,
        "preferences.html",
        {
            "request": request,
            "prefs": prefs,
            "settings": settings,
        },
    )


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, db: Session = Depends(get_db)):
    prefs = get_preferences(db)
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {
            "request": request,
            "prefs": prefs,
            "settings": settings,
            "role_tracks": JOB_PROFILES,
            "profile_groups": PROFILE_GROUPS,
            "skill_map": {k: v["skill_presets"] for k, v in JOB_PROFILES.items()},
            "label_map": {k: v["label"] for k, v in JOB_PROFILES.items()},
        },
    )


_PROFILE_KEYS = {
    "job_profiles",
    "role_tracks",
    "experience_level",
    "preferred_tech",
    "preferred_locations",
    "remote_ok",
    "hybrid_ok",
    "alert_threshold",
    "onboarding_completed",
}


@app.get("/api/profile")
def api_profile_get(db: Session = Depends(get_db)):
    """Return the current user profile (used by the local-first sync layer)."""
    prefs = get_preferences(db)
    return {key: prefs.get(key) for key in sorted(_PROFILE_KEYS | {"profile_updated_at"})}


@app.post("/api/profile")
async def api_profile_save(request: Request, db: Session = Depends(get_db)):
    """Save a profile from onboarding or the local-first sync layer.

    Accepts a JSON object with any of the profile keys; stamps
    profile_updated_at (last-write-wins sync) and re-scores in the background.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)

    updates = {k: v for k, v in payload.items() if k in _PROFILE_KEYS}
    if not updates:
        return JSONResponse({"ok": False, "error": "no valid profile keys"}, status_code=400)

    updates["profile_updated_at"] = datetime.now().isoformat(timespec="seconds")
    prefs = set_preferences(db, updates)

    # Re-score existing jobs in the background so the save returns instantly.
    scheduler.add_job(_rescore_all_jobs)

    return {"ok": True, "profile": {key: prefs.get(key) for key in sorted(_PROFILE_KEYS | {"profile_updated_at"})}}


@app.post("/preferences")
def save_preferences(
    request: Request,
    preferred_tech: str = Form(""),
    preferred_locations: str = Form(""),
    remote_ok: str = Form("off"),
    hybrid_ok: str = Form("off"),
    alert_threshold: str = Form("60"),
    db: Session = Depends(get_db),
):
    updates = {
        "preferred_tech": [t.strip() for t in preferred_tech.split(",") if t.strip()],
        "preferred_locations": [l.strip() for l in preferred_locations.split(",") if l.strip()],
        "remote_ok": remote_ok == "on",
        "hybrid_ok": hybrid_ok == "on",
        "alert_threshold": float(alert_threshold),
    }
    set_preferences(db, updates)

    # Re-score existing jobs in the background so the save request returns instantly.
    scheduler.add_job(_rescore_all_jobs)

    return RedirectResponse(url="/", status_code=303)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


@app.get("/applications", response_class=HTMLResponse)
def applications_page(request: Request, db: Session = Depends(get_db)):
    apps = (
        db.query(Application)
        .join(Job)
        .order_by(Application.applied_at.desc(), Application.updated_at.desc())
        .all()
    )
    grouped = {status: [] for status in APPLICATION_STATUSES}
    for app in apps:
        grouped.setdefault(app.status, []).append(app)
    return templates.TemplateResponse(
        request,
        "applications.html",
        {
            "request": request,
            "settings": settings,
            "grouped": grouped,
            "statuses": APPLICATION_STATUSES,
        },
    )


@app.post("/applications")
def create_application(
    request: Request,
    job_id: int = Form(),
    status: str = Form("saved"),
    applied_at: str = Form(""),
    closing_date: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    if status not in APPLICATION_STATUSES:
        status = "saved"

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return RedirectResponse(url="/", status_code=303)

    application = db.query(Application).filter(Application.job_id == job_id).first()
    if application:
        application.status = status
        application.applied_at = _parse_date(applied_at) or application.applied_at
        application.closing_date = _parse_date(closing_date) or application.closing_date
        application.notes = notes
    else:
        application = Application(
            job_id=job_id,
            status=status,
            applied_at=_parse_date(applied_at),
            closing_date=_parse_date(closing_date),
            notes=notes,
        )
        db.add(application)

    # Tracking no longer hides the job; the dashboard filters tracked jobs
    # by status (saved visible with badge, applied+ hidden unless ?tracked=all).
    db.commit()
    return RedirectResponse(url="/applications", status_code=303)


@app.post("/applications/{application_id}")
def update_application(
    request: Request,
    application_id: int,
    status: str = Form("saved"),
    applied_at: str = Form(""),
    closing_date: str = Form(""),
    notes: str = Form(""),
    outcome: str = Form(""),
    db: Session = Depends(get_db),
):
    if status not in APPLICATION_STATUSES:
        status = "saved"

    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        return RedirectResponse(url="/applications", status_code=303)

    application.status = status
    if applied_at:
        application.applied_at = _parse_date(applied_at)
    if closing_date:
        application.closing_date = _parse_date(closing_date)
    application.notes = notes
    application.outcome = outcome

    db.commit()
    return RedirectResponse(url="/applications", status_code=303)


@app.post("/applications/{application_id}/delete")
def delete_application(application_id: int, db: Session = Depends(get_db)):
    application = db.query(Application).filter(Application.id == application_id).first()
    if application:
        job = application.job
        db.delete(application)
        job.hidden = False
        db.commit()
    return RedirectResponse(url="/applications", status_code=303)


async def _rescore_all_jobs():
    """Re-score every job row using the latest preferences."""
    await asyncio.sleep(0.5)  # let the redirect response finish first
    db = next(get_db())
    try:
        prefs = get_preferences(db)
        total = 0
        batch_size = 100
        for job in db.query(Job).yield_per(batch_size):
            scores = score_job(
                title=job.title or "",
                description=job.description or "",
                location=job.location or "",
                prefs=prefs,
                remote=job.remote,
                hybrid=job.hybrid,
                company_size=job.company_size,
                company_founded=job.company_founded,
                company_perks=job.company_perks or [],
            )
            job.score = scores["score"]
            job.learning_score = scores["learning_score"]
            job.worklife_score = scores["worklife_score"]
            job.tech_score = scores["tech_score"]
            job.company_score = scores["company_score"]
            job.updated_at = datetime.utcnow()
            total += 1
            if total % batch_size == 0:
                db.commit()
        db.commit()
        logger.info("Re-scored %d jobs in background with new preferences", total)
    except Exception as exc:
        logger.error("Background re-scoring failed: %s", exc)
    finally:
        db.close()


@app.post("/hide/{job_id}")
def hide_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.hidden = True
        db.commit()
    return {"ok": True}


@app.post("/fetch")
async def trigger_fetch(db: Session = Depends(get_db)):
    await fetch_and_process()
    total = db.query(Job).filter(Job.hidden == False).count()
    new = db.query(Job).filter(Job.is_new == True).count()
    return {
        "ok": True,
        "total_visible": total,
        "new_jobs": new,
    }


@app.get("/api/jobs")
def api_jobs(
    db: Session = Depends(get_db),
    min_score: float = 0.0,
    skip: int = 0,
    limit: int = 100,
):
    jobs = (
        db.query(Job)
        .filter(Job.hidden == False, Job.score >= min_score, _allowed_location_clause())
        .order_by(Job.score.desc(), Job.date_posted.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": j.id,
            "source": j.source,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "score": j.score,
            "learning_score": j.learning_score,
            "worklife_score": j.worklife_score,
            "tech_score": j.tech_score,
            "company_score": j.company_score,
            "url": j.url,
            "date_posted": j.date_posted.isoformat() if j.date_posted else None,
            "is_new": j.is_new,
            "remote": j.remote,
            "hybrid": j.hybrid,
            "salary_text": j.salary_text,
        }
        for j in jobs
    ]

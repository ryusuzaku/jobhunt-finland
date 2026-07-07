import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings
from src.models import Base, engine, get_db, Job
from src.scorer import score_job
from src.scraper import fetch_all_jobs, save_jobs, prune_stale_jobs
from src.alerts import send_console_alerts, send_email_alerts, send_discord_alerts, send_slack_alerts
from src.preferences import get_preferences, set_preferences

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="src/templates")


async def fetch_and_process():
    """Fetch jobs, score them, save to DB, and send alerts."""
    db = next(get_db())
    try:
        prefs = get_preferences(db)
        logger.info("Starting job fetch...")
        raw, fetched_sources = await fetch_all_jobs()
        new, updated = save_jobs(db, raw, prefs)
        logger.info("Saved %d new jobs, updated %d existing jobs", new, updated)
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
    logger.info("Scheduler started. Fetching jobs on startup...")
    await fetch_and_process()
    yield
    scheduler.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/static"), name="static")


def _dashboard_context(request: Request, db: Session):
    jobs = (
        db.query(Job)
        .filter(Job.hidden == False)
        .order_by(Job.score.desc(), Job.date_posted.desc())
        .limit(100)
        .all()
    )
    scores = [j.score for j in jobs]
    avg_score = round(sum(scores) / len(scores), 0) if scores else 0
    prefs = get_preferences(db)

    # Distinct sources in the whole DB so filters show every source,
    # not just the ones that happen to be in the top 100.
    sources = sorted(
        {row[0] for row in db.query(Job.source).distinct() if row[0]}
    )

    return {
        "request": request,
        "jobs": jobs,
        "avg_score": avg_score,
        "settings": settings,
        "prefs": prefs,
        "sources": sources,
    }


@app.get("/api/locations")
def api_locations(db: Session = Depends(get_db)):
    """Return distinct non-empty locations from visible jobs for the town filter."""
    rows = db.query(Job.location).filter(Job.hidden == False).distinct().all()
    return sorted(
        {(r[0] or "").strip().lower() for r in rows if (r[0] or "").strip()}
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "index.html",
        _dashboard_context(request, db),
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
    asyncio.get_event_loop().create_task(_rescore_all_jobs_in_background())

    return RedirectResponse(url="/", status_code=303)


async def _rescore_all_jobs_in_background():
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
def api_jobs(db: Session = Depends(get_db), min_score: float = 0.0, limit: int = 100):
    jobs = (
        db.query(Job)
        .filter(Job.hidden == False, Job.score >= min_score)
        .order_by(Job.score.desc(), Job.date_posted.desc())
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

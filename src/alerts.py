import logging
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from src.config import settings
from src.models import Job

logger = logging.getLogger(__name__)


def get_alert_candidates(db: Session, threshold: float | None = None) -> list[Job]:
    """Return new, non-alerted jobs above the alert threshold, ordered by score."""
    if threshold is None:
        threshold = settings.alert_threshold
    return (
        db.query(Job)
        .filter(Job.is_new == True, Job.alerted == False, Job.hidden == False)
        .filter(Job.score >= threshold)
        .order_by(Job.score.desc())
        .all()
    )


def format_alert(job: Job) -> str:
    return (
        f"🎯 {job.title}\n"
        f"   Company: {job.company}\n"
        f"   Location: {job.location}\n"
        f"   Score: {job.score} (learning {job.learning_score}, "
        f"worklife {job.worklife_score}, tech {job.tech_score}, company {job.company_score})\n"
        f"   {job.url}\n"
    )


def _mark_alerted(db: Session, jobs: list[Job]) -> None:
    for job in jobs:
        job.alerted = True
    db.commit()


def send_console_alerts(db: Session, jobs: list[Job] | None = None) -> list[Job]:
    """Print alert candidates to the console and mark them alerted."""
    if jobs is None:
        jobs = get_alert_candidates(db)
    if not jobs:
        logger.info("No new high-scoring jobs to alert.")
        return []

    logger.info("=== %d NEW HIGH-SCORE JOBS ===", len(jobs))
    for job in jobs:
        logger.info(format_alert(job))
    _mark_alerted(db, jobs)
    return jobs


def send_email_alerts(db: Session, jobs: list[Job] | None = None) -> list[Job]:
    """Send email alerts if SMTP is configured."""
    if jobs is None:
        jobs = get_alert_candidates(db)
    if not jobs:
        return []

    if not all([settings.alert_email, settings.smtp_host, settings.smtp_user, settings.smtp_password]):
        logger.info("SMTP not configured; skipping email alerts.")
        return []

    body = "New high-scoring junior tech jobs in Finland:\n\n"
    body += "\n".join(format_alert(job) for job in jobs)

    msg = EmailMessage()
    msg["Subject"] = f"JobHunt FI: {len(jobs)} new high-score jobs"
    msg["From"] = settings.smtp_user
    msg["To"] = settings.alert_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("Email alert sent to %s for %d jobs", settings.alert_email, len(jobs))
        _mark_alerted(db, jobs)
    except Exception as exc:
        logger.error("Failed to send email alert: %s", exc)

    return jobs


def send_discord_alerts(db: Session, jobs: list[Job] | None = None) -> list[Job]:
    """Send Discord webhook alerts if configured."""
    if jobs is None:
        jobs = get_alert_candidates(db)
    if not jobs or not settings.discord_webhook_url:
        return jobs

    for job in jobs:
        payload = {
            "content": None,
            "embeds": [
                {
                    "title": job.title,
                    "url": job.url,
                    "description": f"{job.company} · {job.location}",
                    "color": 3447003,
                    "fields": [
                        {"name": "Score", "value": str(job.score), "inline": True},
                        {"name": "Learning", "value": str(job.learning_score), "inline": True},
                        {"name": "Work-life", "value": str(job.worklife_score), "inline": True},
                        {"name": "Tech", "value": str(job.tech_score), "inline": True},
                        {"name": "Company", "value": str(job.company_score), "inline": True},
                    ],
                }
            ],
        }
        try:
            httpx.post(settings.discord_webhook_url, json=payload, timeout=20)
        except Exception as exc:
            logger.error("Discord alert failed: %s", exc)

    logger.info("Discord alerts sent for %d jobs", len(jobs))
    _mark_alerted(db, jobs)
    return jobs


def send_slack_alerts(db: Session, jobs: list[Job] | None = None) -> list[Job]:
    """Send Slack webhook alerts if configured."""
    if jobs is None:
        jobs = get_alert_candidates(db)
    if not jobs or not settings.slack_webhook_url:
        return jobs

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎯 {len(jobs)} new high-score jobs"},
        }
    ]
    for job in jobs:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{job.url}|{job.title}>*\n{job.company} · {job.location} · Score: {job.score}",
            },
        })

    try:
        httpx.post(settings.slack_webhook_url, json={"blocks": blocks}, timeout=20)
    except Exception as exc:
        logger.error("Slack alert failed: %s", exc)

    logger.info("Slack alerts sent for %d jobs", len(jobs))
    _mark_alerted(db, jobs)
    return jobs

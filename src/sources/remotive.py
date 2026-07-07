import logging
from datetime import datetime

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_CATEGORIES = [
    "software-dev",
    "data",
    "devops",
    "sys-admin",
    "web-dev",
    "mobile-dev",
    "qa",
]

_ACCEPTABLE_REMOTE_LOCATIONS = [
    "finland", "europe", "eu", "emea", "nordic", "baltic",
    "anywhere", "worldwide", "global", "remote", "fully remote",
    "work from home", "distributed", "multiple countries",
]


def _is_acceptable_remote(location: str) -> bool:
    low = location.lower()
    if any(term in low for term in _ACCEPTABLE_REMOTE_LOCATIONS):
        return True
    if not location.strip():
        return True
    if any(term in low for term in ["united states", "usa", "us only", "canada only", "uk only"]):
        return False
    return True


class RemotiveSource:
    name = "remotive"

    def __init__(self):
        self.base_url = "https://remotive.com/api/remote-jobs"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        seen = set()

        for category in _CATEGORIES:
            url = f"{self.base_url}?category={category}"
            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": settings.user_agent},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("Remotive error for category %s: %s", category, exc)
                continue

            for job in data.get("jobs", []):
                job_id = str(job.get("id"))
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                title = job.get("title") or ""
                location = job.get("candidate_required_location") or ""
                if not _is_acceptable_remote(location):
                    continue
                if "\ufffd" in f"{title} {location}":
                    continue
                results.append(job)

        logger.info("Remotive fetched %d jobs", len(results))
        return results

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title") or ""
        company = raw.get("company_name") or ""
        location = raw.get("candidate_required_location") or "Remote"
        description = raw.get("description") or ""
        full_text = f"{title} {description}".lower()

        date_posted = datetime.utcnow()
        pub = raw.get("publication_date")
        if pub:
            try:
                date_posted = datetime.fromisoformat(pub)
            except ValueError:
                pass

        return {
            "source": self.name,
            "source_id": str(raw.get("id")),
            "title": title,
            "company": company,
            "location": location,
            "description": description or f"{title} at {company}",
            "url": raw.get("url") or "",
            "date_posted": date_posted,
            "salary_text": None,
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
            "remote": True,
            "hybrid": "hybrid" in full_text,
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": raw.get("tags") or [],
        }

import logging
from datetime import datetime
from html import unescape

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

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


def _is_tech_role(title: str, tags: str, category: str) -> bool:
    combined = f"{title} {tags} {category}".lower()
    tech_signals = [
        "software", "developer", "engineer", "data", "devops", "cloud",
        "frontend", "backend", "full stack", "fullstack", "web", "mobile",
        "python", "javascript", "typescript", "react", "node", "java",
        "ai", "machine learning", "ml", "analytics", "security", "qa", "test",
        "support", "sysadmin", "database", "sql", "aws", "azure", "gcp",
    ]
    return any(sig in combined for sig in tech_signals)


class WorkingNomadsSource:
    name = "workingnomads"

    def __init__(self):
        self.api_url = "https://www.workingnomads.com/api/exposed_jobs/"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(
                self.api_url,
                headers={"User-Agent": settings.user_agent},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Working Nomads API error: %s", exc)
            return []

        results: list[dict] = []
        for job in data:
            if not isinstance(job, dict):
                continue
            title = unescape(job.get("title") or "")
            tags = job.get("tags") or ""
            category = job.get("category_name") or ""
            location = job.get("location") or ""
            if not _is_tech_role(title, tags, category):
                continue
            if not _is_acceptable_remote(location):
                continue
            if "\ufffd" in f"{title} {location}":
                continue
            results.append(job)

        logger.info("Working Nomads fetched %d tech jobs", len(results))
        return results

    def normalize(self, raw: dict) -> dict:
        title = unescape(raw.get("title") or "")
        company = unescape(raw.get("company_name") or "")
        location = raw.get("location") or "Remote"
        description = unescape(raw.get("description") or "")
        full_text = f"{title} {description}".lower()

        date_posted = datetime.utcnow()
        pub = raw.get("pub_date")
        if pub:
            try:
                date_posted = datetime.strptime(pub, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                try:
                    date_posted = datetime.fromisoformat(pub)
                except ValueError:
                    pass

        # The URL from the API is a Working Nomads redirect; use it as-is.
        url = raw.get("url") or ""
        source_id = url.rstrip("/").split("/")[-1] or title

        return {
            "source": self.name,
            "source_id": source_id,
            "title": title,
            "company": company,
            "location": location,
            "description": description or f"{title} at {company}",
            "url": url,
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
            "company_perks": (raw.get("tags") or "").split(","),
        }

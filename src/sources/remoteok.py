import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Locations we consider acceptable for remote-only boards.  Finland/Europe/
# EMEA/Anywhere/Global are kept; country-specific US/Canada-only postings are
# dropped because the user wants remote jobs only when they are Finland-based.
_ACCEPTABLE_REMOTE_LOCATIONS = [
    "finland", "europe", "eu", "emea", "nordic", "baltic",
    "anywhere", "worldwide", "global", "remote", "fully remote",
    "work from home", "distributed", "multiple countries",
]

_TECH_KEYWORDS = [
    "software", "developer", "engineer", "data", "devops", "cloud",
    "frontend", "backend", "full stack", "fullstack", "web", "mobile",
    "python", "javascript", "typescript", "react", "node", "java", "kotlin",
    "ai", "machine learning", "ml", "analytics", "security", "qa", "test",
    "support", "sysadmin", "database", "sql", "aws", "azure", "gcp",
]


def _is_acceptable_remote(location: str) -> bool:
    low = location.lower()
    # Explicit region matches
    if any(term in low for term in _ACCEPTABLE_REMOTE_LOCATIONS):
        return True
    # Blank locations are usually "remote" but unspecified; keep them and let
    # the user filter later.
    if not location.strip():
        return True
    # Drop obvious US/Canada-only postings
    if any(term in low for term in ["united states", "usa", "us only", "canada only", "uk only"]):
        return False
    return True


def _is_tech_role(title: str, tags: list[str]) -> bool:
    low_title = title.lower()
    # Require the title itself to contain a strong tech signal so generic
    # "Customer Support" / "Administrative Assistant" postings don't slip in.
    if any(kw in low_title for kw in _TECH_KEYWORDS):
        return True
    tags_low = ' '.join(tags).lower()
    return any(kw in tags_low for kw in ["developer", "engineer", "devops", "data", "software"])


class RemoteOKSource:
    name = "remoteok"

    def __init__(self):
        self.api_url = "https://remoteok.com/api"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(
                self.api_url,
                headers={"User-Agent": settings.user_agent},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Remote OK API error: %s", exc)
            return []

        results: list[dict] = []
        for item in data:
            # The first item is metadata, not a job.
            if not isinstance(item, dict) or not item.get("id"):
                continue
            title = item.get("position") or ""
            tags = item.get("tags") or []
            location = item.get("location") or ""
            if not _is_tech_role(title, tags):
                continue
            if not _is_acceptable_remote(location):
                continue
            # Drop postings where the location is garbled/mojibake.
            if "\ufffd" in location or "\ufffd" in title:
                continue
            results.append(item)

        logger.info("Remote OK fetched %d tech jobs", len(results))
        return results

    def normalize(self, raw: dict) -> dict:
        title = raw.get("position") or ""
        company = raw.get("company") or ""
        location = raw.get("location") or "Remote"
        slug = raw.get("slug") or str(raw.get("id"))
        description = raw.get("description") or ""
        tags = raw.get("tags") or []
        full_text = f"{title} {description} {' '.join(tags)}".lower()

        date_posted = datetime.utcnow()
        date_str = raw.get("date")
        if date_str:
            try:
                date_posted = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        return {
            "source": self.name,
            "source_id": slug,
            "title": title,
            "company": company,
            "location": location,
            "description": description or f"{title} at {company}",
            "url": urljoin("https://remoteok.com/remote-jobs/", slug),
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
            "company_perks": [],
        }

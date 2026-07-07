import logging
import re
from datetime import datetime
from html import unescape
from xml.etree import ElementTree as ET

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_FEED_URL = "https://weworkremotely.com/remote-jobs.rss"

_TECH_CATEGORIES = {
    "programming", "devops", "backend", "frontend", "full-stack", "full stack",
    "mobile", "qa", "data", "security", "sysadmin", "web dev", "software",
}

_ACCEPTABLE_REMOTE_LOCATIONS = [
    "finland", "europe", "eu", "emea", "nordic", "baltic",
    "anywhere", "worldwide", "global", "remote", "fully remote",
    "work from home", "distributed", "multiple countries",
]


def _is_acceptable_remote(text: str) -> bool:
    low = text.lower()
    if any(term in low for term in _ACCEPTABLE_REMOTE_LOCATIONS):
        return True
    if any(term in low for term in ["united states", "usa", "us only", "canada only", "uk only"]):
        return False
    return True


def _is_tech_category(title: str, categories: list[str]) -> bool:
    combined = f"{title} {' '.join(categories)}".lower()
    return any(cat in combined for cat in _TECH_CATEGORIES)


class WeWorkRemotelySource:
    name = "weworkremotely"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(
                _FEED_URL,
                headers={
                    "User-Agent": settings.user_agent,
                    "Accept": "application/rss+xml,application/xml,text/xml",
                },
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("We Work Remotely RSS error: %s", exc)
            return []

        try:
            root = ET.fromstring(resp.text)
            channel = root.find("channel")
            items = channel.findall("item") if channel is not None else []
        except Exception as exc:
            logger.warning("Failed to parse We Work Remotely RSS: %s", exc)
            return []

        results: list[dict] = []
        for item in items:
            title = (item.findtext("title", "") or "").strip()
            link = (item.findtext("link", "") or "").strip()
            description = (item.findtext("description", "") or "").strip()
            pub_date = (item.findtext("pubDate", "") or "").strip()
            categories = [c.text or "" for c in item.findall("category")]

            if not title or not link:
                continue
            if not _is_tech_category(title, categories):
                continue
            if not _is_acceptable_remote(f"{title} {description}"):
                continue
            if "\ufffd" in f"{title} {description}":
                continue

            results.append({
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date,
                "categories": categories,
            })

        logger.info("We Work Remotely fetched %d tech jobs", len(results))
        return results

    def normalize(self, raw: dict) -> dict:
        title = unescape(raw.get("title", ""))
        link = raw.get("link", "")
        description = raw.get("description", "")
        full_text = f"{title} {description}".lower()

        # WWR titles are usually "Company: Role"
        company = ""
        role = title
        if ":" in title:
            company, _, role = title.partition(":")
            company = company.strip()
            role = role.strip()

        # Try to extract headquarters from the description
        location = "Remote"
        hq_match = re.search(r"Headquarters:</strong>\s*([^<]+)", description)
        if hq_match:
            location = unescape(hq_match.group(1).strip())

        date_posted = datetime.utcnow()
        pub = raw.get("pub_date")
        if pub:
            try:
                date_posted = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
            except ValueError:
                pass

        source_id = link.rstrip("/").split("/")[-1] or title

        return {
            "source": self.name,
            "source_id": source_id,
            "title": role,
            "company": company,
            "location": location,
            "description": description,
            "url": link,
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

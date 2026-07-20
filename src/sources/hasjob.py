import logging
from datetime import datetime
from xml.etree import ElementTree

import httpx

from src.config import settings
from src.scorer import extract_salary
from src.sources.india_common import (
    is_bengaluru_location,
    is_junior_friendly,
    is_tech_role,
    strip_html,
)

logger = logging.getLogger(__name__)

_ATOM_NS = "{http://www.w3.org/2005/Atom}"


class HasjobSource:
    """Hasjob (India tech job board) Atom feed source."""

    name = "hasjob"

    def __init__(self):
        self.feed_url = "https://hasjob.co/feed"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(
                self.feed_url,
                headers={"User-Agent": settings.user_agent},
            )
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.text)
        except Exception as exc:
            logger.warning("Hasjob feed error: %s", exc)
            return []

        results: list[dict] = []
        for entry in root.findall(f"{_ATOM_NS}entry"):
            title = (entry.findtext(f"{_ATOM_NS}title") or "").strip()
            location = (entry.findtext(f"{_ATOM_NS}location") or "").strip()
            link_el = entry.find(f"{_ATOM_NS}link")
            link = link_el.get("href") if link_el is not None else ""
            published = (
                entry.findtext(f"{_ATOM_NS}published")
                or entry.findtext(f"{_ATOM_NS}updated")
                or ""
            )
            content_html = entry.findtext(f"{_ATOM_NS}content") or ""
            description = strip_html(content_html)

            if not title or not link:
                continue
            if not is_bengaluru_location(location):
                continue
            if not is_tech_role(title, description):
                continue
            if not is_junior_friendly(title):
                continue

            # Company is the first <strong><a> inside the content HTML.
            company = self._extract_company(content_html)

            results.append(
                {
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description,
                    "url": link,
                    "published": published,
                }
            )

        logger.info("Hasjob fetched %d Bengaluru tech jobs", len(results))
        return results

    @staticmethod
    def _extract_company(content_html: str) -> str:
        import re

        m = re.search(r"<strong>\s*<a[^>]*>(.*?)</a>", content_html or "", re.S)
        if m:
            return strip_html(m.group(1))
        return ""

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.utcnow()

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title") or ""
        description = raw.get("description") or ""
        full_text = f"{title} {description}"
        salary = extract_salary(full_text)

        return {
            "source": self.name,
            "source_id": (raw.get("url") or "").rstrip("/").split("/")[-1] or title,
            "title": title,
            "company": raw.get("company") or "",
            "location": raw.get("location") or "",
            "description": description or f"{title} at {raw.get('company')}",
            "url": raw.get("url") or "",
            "date_posted": self._parse_date(raw.get("published")),
            "salary_text": salary["text"] if salary else None,
            "salary_min": salary["min"] if salary else None,
            "salary_max": salary["max"] if salary else None,
            "salary_currency": salary["currency"] if salary else None,
            "salary_period": salary["period"] if salary else None,
            "remote": "remote" in full_text.lower(),
            "hybrid": "hybrid" in full_text.lower(),
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": [],
        }

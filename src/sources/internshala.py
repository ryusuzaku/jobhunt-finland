import asyncio
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scorer import extract_salary
from src.sources.india_common import (
    is_bengaluru_location,
    is_junior_friendly,
    is_tech_role,
    parse_relative_date,
)

logger = logging.getLogger(__name__)

_CARD_SELECTOR = "div.individual_internship"


class InternshalaSource:
    """Internshala fresher jobs (Bengaluru tech roles)."""

    name = "internshala"

    def __init__(self):
        self.base_url = "https://internshala.com"
        self.search_terms = settings.indian_search_terms
        self.max_pages_per_term = 1
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @staticmethod
    def _slug(term: str) -> str:
        return "-".join(term.lower().split())

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        seen_ids: set[str] = set()

        for term in self.search_terms:
            for page in range(1, self.max_pages_per_term + 1):
                url = f"{self.base_url}/jobs/{self._slug(term)}-jobs/"
                if page > 1:
                    url = f"{url}page-{page}/"
                try:
                    resp = await client.get(url, headers=self.headers)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.warning("Internshala error for '%s' page %d: %s", term, page, exc)
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = [
                    c for c in soup.select(_CARD_SELECTOR)
                    if (c.get("employment_type") or "job") == "job"
                ]
                if not cards:
                    break

                for card in cards:
                    parsed = self._parse_card(card)
                    if not parsed:
                        continue
                    if parsed["source_id"] in seen_ids:
                        continue
                    seen_ids.add(parsed["source_id"])
                    results.append(parsed)

                await asyncio.sleep(1.0)

        logger.info("Internshala fetched %d Bengaluru tech jobs", len(results))
        return results

    def _parse_card(self, card) -> dict | None:
        title_el = card.select_one("a.job-title-href")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        href = title_el.get("href") or card.get("data-href") or ""
        url = urljoin(self.base_url, href)
        source_id = card.get("internshipid") or href.rstrip("/").split("-")[-1] or title

        company_el = card.select_one("p.company-name")
        company = company_el.get_text(strip=True) if company_el else ""
        # Company names sometimes carry a location suffix: "Acme (Mumbai, India)".
        if "(" in company:
            company = company.split("(")[0].strip()

        location_el = card.select_one("p.row-1-item.locations span")
        location = location_el.get_text(" ", strip=True) if location_el else ""

        salary_text = ""
        for div in card.select("div.row-1-item"):
            icon = div.find("i")
            if icon and "ic-16-money" in (icon.get("class") or []):
                span = div.select_one("span.mobile") or div.select_one("span.desktop")
                salary_text = span.get_text(strip=True) if span else ""
                break

        experience = ""
        for div in card.select("div.row-1-item"):
            icon = div.find("i")
            if icon and "ic-16-briefcase" in (icon.get("class") or []):
                span = div.find("span")
                experience = span.get_text(strip=True) if span else ""
                break

        desc_el = card.select_one("div.about_job div.text")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        skills = [s.get_text(strip=True) for s in card.select("div.job_skill")]

        posted_el = card.select_one("div.status-info span")
        posted_text = posted_el.get_text(strip=True) if posted_el else ""

        if not is_bengaluru_location(location):
            return None
        if not is_tech_role(title, " ".join(skills) or description):
            return None
        if not is_junior_friendly(title, experience):
            return None

        return {
            "source": self.name,
            "source_id": str(source_id),
            "title": title,
            "company": company,
            "location": location,
            "description": description or f"{title} at {company}, {location}",
            "url": url,
            "posted_text": posted_text,
            "salary_text_raw": salary_text,
            "skills": skills,
        }

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title") or ""
        salary = extract_salary(raw.get("salary_text_raw") or "")
        full_text = f"{title} {raw.get('description') or ''} {raw.get('location') or ''}".lower()

        return {
            "source": self.name,
            "source_id": raw.get("source_id"),
            "title": title,
            "company": raw.get("company") or "",
            "location": raw.get("location") or "",
            "description": raw.get("description") or title,
            "url": raw.get("url") or "",
            "date_posted": parse_relative_date(raw.get("posted_text")),
            "salary_text": salary["text"] if salary else (raw.get("salary_text_raw") or None),
            "salary_min": salary["min"] if salary else None,
            "salary_max": salary["max"] if salary else None,
            "salary_currency": salary["currency"] if salary else None,
            "salary_period": salary["period"] if salary else None,
            "remote": "work from home" in full_text or "remote" in full_text,
            "hybrid": "hybrid" in full_text,
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": raw.get("skills") or [],
        }

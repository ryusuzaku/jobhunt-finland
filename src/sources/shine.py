import asyncio
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scorer import extract_salary
from src.sources.india_common import (
    is_agency_spam,
    is_bengaluru_location,
    is_junior_friendly,
    is_tech_role,
    parse_relative_date,
)

logger = logging.getLogger(__name__)

_CARD_SELECTOR = "div.jobCardNova_bigCard__W2xn3"


class ShineSource:
    """Shine.com HTML search results (Bengaluru tech jobs)."""

    name = "shine"

    def __init__(self):
        self.base_url = "https://www.shine.com"
        self.search_terms = settings.indian_search_terms
        self.max_pages_per_term = 1  # keep request volume low
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
                url = f"{self.base_url}/job-search/{self._slug(term)}-jobs-in-bengaluru"
                if page > 1:
                    url = f"{url}-{page}"
                try:
                    resp = await client.get(url, headers=self.headers)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.warning("Shine error for '%s' page %d: %s", term, page, exc)
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(_CARD_SELECTOR)
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

        logger.info("Shine fetched %d Bengaluru tech jobs", len(results))
        return results

    def _parse_card(self, card) -> dict | None:
        title_el = card.select_one("h3.jdTruncation a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        href = title_el.get("href") or ""
        url = urljoin(self.base_url, href)
        source_id = href.rstrip("/").split("/")[-1] or title

        company_el = card.select_one("span.jdTruncationCompany")
        company = company_el.get_text(strip=True) if company_el else ""

        posted_el = card.select_one("span.jobCardNova_postedData__LTERc")
        posted_text = posted_el.get_text(" ", strip=True) if posted_el else ""

        # Experience and salary share the same classes; distinguish by icon alt.
        experience = ""
        salary_text = ""
        for div in card.select("div.jdbigCardExperience"):
            img = div.find("img")
            span = div.find("span")
            if not span:
                continue
            alt = (img.get("alt") or "").lower() if img else ""
            if "salary" in alt:
                salary_text = span.get_text(strip=True)
            else:
                experience = span.get_text(strip=True)

        location_el = card.select_one("div.jobCardNova_bigCardCenterListLoc__usiPB span")
        location = location_el.get_text(strip=True) if location_el else ""

        skills = [li.get_text(strip=True) for li in card.select("ul.jobCardNova_skillsLists__7YifX li")]

        if not is_bengaluru_location(location):
            return None
        if is_agency_spam(company, title):
            return None
        if not is_tech_role(title, " ".join(skills)):
            return None
        if not is_junior_friendly(title, experience):
            return None

        return {
            "source": self.name,
            "source_id": source_id,
            "title": title,
            "company": company,
            "location": location,
            "description": f"{title} at {company}, {location}. Skills: {', '.join(skills)}. Experience: {experience}",
            "url": url,
            "posted_text": posted_text,
            "salary_text_raw": salary_text,
            "skills": skills,
        }

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title") or ""
        salary = extract_salary(raw.get("salary_text_raw") or "")
        full_text = f"{title} {raw.get('description') or ''}".lower()

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
            "remote": "remote" in full_text,
            "hybrid": "hybrid" in full_text,
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": raw.get("skills") or [],
        }

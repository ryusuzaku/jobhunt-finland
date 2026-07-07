import asyncio
import html
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)

# Module-level cooldown tracker so scheduled runs remember a recent 429.
_rate_limited_until: datetime | None = None


class LinkedInSource:
    """
    Lightweight LinkedIn guest-job search scraper.

    Uses LinkedIn's public guest endpoint to avoid login.  It deliberately
    keeps request volume low (a couple of pages per keyword per location, no
    detail-page fetching) to minimise the chance of hitting LinkedIn's rate
    limits / bot detection.

    If a 429 response is seen, the source backs off for two hours before
    trying again.
    """

    name = "linkedin"
    cooldown_minutes = 120

    def __init__(self):
        self.base_url = "https://www.linkedin.com"
        self.search_url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        )
        self.search_terms = [
            "junior software developer",
            "software engineer",
            "data engineer",
            "full stack developer",
            "backend developer",
            "frontend developer",
        ]
        # Locations to search. Pages are 10-job increments (start=0,10,20...).
        self.locations = [
            {"location": "Finland", "pages": 2},
            {"location": "Bengaluru, Karnataka, India", "pages": 2},
        ]
        self.headers = {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @property
    def is_rate_limited(self) -> bool:
        global _rate_limited_until
        if _rate_limited_until is None:
            return False
        if datetime.utcnow() >= _rate_limited_until:
            _rate_limited_until = None
            return False
        return True

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        global _rate_limited_until

        if self.is_rate_limited:
            logger.warning(
                "LinkedIn is rate-limited; cooling down until %s",
                _rate_limited_until.isoformat(),
            )
            return []

        results: list[dict] = []
        seen_ids = set()
        rate_limited = False

        for loc_config in self.locations:
            if rate_limited:
                break
            location = loc_config["location"]
            pages = loc_config["pages"]
            is_finland = "finland" in location.lower()

            for term in self.search_terms:
                if rate_limited:
                    break
                for page in range(pages):
                    start = page * 10
                    params = {
                        "keywords": term,
                        "location": location,
                        "start": start,
                    }
                    try:
                        resp = await client.get(
                            self.search_url, params=params, headers=self.headers
                        )
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            _rate_limited_until = datetime.utcnow() + timedelta(
                                minutes=self.cooldown_minutes
                            )
                            logger.warning(
                                "LinkedIn rate limited (429) for '%s' / '%s'; cooling down until %s",
                                term,
                                location,
                                _rate_limited_until.isoformat(),
                            )
                            rate_limited = True
                        else:
                            logger.warning(
                                "LinkedIn search failed for '%s' / '%s' start %d: %s",
                                term,
                                location,
                                start,
                                exc,
                            )
                        break
                    except Exception as exc:
                        logger.warning(
                            "LinkedIn search failed for '%s' / '%s' start %d: %s",
                            term,
                            location,
                            start,
                            exc,
                        )
                        break

                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("li")
                    logger.info(
                        "LinkedIn term '%s' / '%s' start %d found %d cards",
                        term,
                        location,
                        start,
                        len(cards),
                    )

                    for card in cards:
                        parsed = self._parse_card(card, is_finland=is_finland)
                        if not parsed:
                            continue
                        if parsed["source_id"] in seen_ids:
                            continue
                        seen_ids.add(parsed["source_id"])
                        results.append(parsed)

                    # Pause between requests to keep LinkedIn from rate-limiting.
                    await asyncio.sleep(1.2)

        return results

    def _parse_card(self, card, is_finland: bool) -> dict | None:
        title_el = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        location_el = card.find("span", class_="job-search-card__location")
        time_el = card.find("time")
        link_el = card.find("a", class_="base-card__full-link", href=True)

        title = html.unescape(title_el.get_text(strip=True)) if title_el else ""
        company = ""
        if company_el:
            nested = company_el.find("a")
            company = html.unescape(
                nested.get_text(strip=True) if nested else company_el.get_text(strip=True)
            )
        location = html.unescape(location_el.get_text(strip=True)) if location_el else ""

        if not title or not link_el or not location:
            return None

        # For non-Finland searches, skip listings that look remote-only.
        # Finland is allowed to be remote-only because the user trusts Finnish remote.
        if not is_finland:
            low_loc = location.lower()
            low_title = title.lower()
            mentions_remote = "remote" in low_loc or "remote" in low_title
            located_in_target = any(
                city in low_loc
                for city in ["bengaluru", "bangalore", "karnataka", "india"]
            )
            if mentions_remote and not located_in_target:
                return None

        url = urljoin(self.base_url, link_el["href"].split("?")[0])

        source_id = ""
        m = re.search(r"/jobs/view/[^/]+-(\d+)", link_el["href"])
        if m:
            source_id = m.group(1)
        else:
            source_id = url.split("-")[-1].split("/")[-1]

        date_posted = datetime.utcnow()
        if time_el and time_el.get("datetime"):
            try:
                date_posted = datetime.fromisoformat(time_el["datetime"].strip())
            except ValueError:
                pass

        full_text = f"{title} {location}".lower()

        return {
            "source": self.name,
            "source_id": source_id,
            "title": title,
            "company": company,
            "location": location,
            "description": f"{title} at {company}, {location}",
            "url": url,
            "date_posted": date_posted,
            "salary_text": None,
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
            "remote": "remote" in full_text,
            "hybrid": "hybrid" in full_text,
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": [],
        }

    def normalize(self, raw: dict) -> dict:
        return raw

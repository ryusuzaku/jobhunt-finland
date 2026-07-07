import logging
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scorer import extract_salary

logger = logging.getLogger(__name__)


class EnglishJobsSource:
    name = "englishjobs"

    def __init__(self):
        self.search_terms = ["developer", "data", "software", "engineer"]

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        for term in self.search_terms:
            url = f"{settings.englishjobs_base_url}/{term}"
            try:
                resp = await client.get(url, headers={"User-Agent": settings.user_agent})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                jobs = soup.find_all("div", class_="job")
                for j in jobs:
                    parsed = self._parse_job(j, url)
                    if parsed:
                        results.append(parsed)
            except Exception as exc:
                logger.warning("EnglishJobs.fi error for term '%s': %s", term, exc)

        seen = set()
        unique: list[dict] = []
        for job in results:
            key = job.get("source_id")
            if key and key not in seen:
                seen.add(key)
                unique.append(job)
        logger.info("EnglishJobs.fi fetched %d unique jobs", len(unique))
        return unique

    def normalize(self, raw: dict) -> dict:
        return raw

    def _parse_job(self, element: BeautifulSoup, base_url: str) -> dict | None:
        link = element.find("a", class_="js-joblink")
        if not link:
            return None

        title = link.get_text(strip=True)
        href = link.get("href") or ""
        url = urljoin(base_url, href)

        # Extract source_id from clickout URL
        source_id = href.split("?")[0].split("/")[-1] if href else title

        # Meta list: company, location, date
        meta_div = element.find("div", class_="flex flex-col sm:flex-row")
        meta = []
        if meta_div:
            meta = [li.get_text(strip=True) for li in meta_div.find_all("li")]

        company = meta[0] if len(meta) > 0 else ""
        location = meta[1] if len(meta) > 1 else ""
        date_text = meta[2] if len(meta) > 2 else ""

        # Description snippet
        desc_div = element.find("div", class_=lambda c: c and "text-gray-400" in c)
        description = desc_div.get_text(" ", strip=True) if desc_div else ""

        full_text = f"{title} {description}"
        salary = extract_salary(full_text)

        date_posted = self._parse_date(date_text)

        return {
            "source": self.name,
            "source_id": source_id,
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "url": url,
            "date_posted": date_posted,
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

    @staticmethod
    def _parse_date(date_text: str) -> datetime | None:
        if not date_text:
            return None
        # Examples: "April 6", "June 26"
        try:
            return datetime.strptime(date_text.strip(), "%B %d")
        except ValueError:
            pass
        try:
            return datetime.strptime(date_text.strip(), "%b %d")
        except ValueError:
            return None

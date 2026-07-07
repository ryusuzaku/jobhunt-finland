import html
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scorer import extract_salary

logger = logging.getLogger(__name__)

# Tech signals used to keep only relevant postings
TECH_KEYWORDS = [
    "software", "developer", "engineer", "data", "it-", "it ", "tech", "programmer",
    "analyst", "cloud", "devops", "security", "web", "mobile", "backend", "frontend",
    "fullstack", "full stack", "ai", "machine learning", "python", "java", "javascript",
    "react", "kotlin", "php", ".net", "azure", "aws", "sap", "consultant", "system",
    "crm", "integration", "embedded", "network", "test", "qa", "support", "administrator",
]


class AcademicWorkSource:
    name = "academicwork"

    def __init__(self):
        self.base_url = "https://www.academicwork.fi"
        self.listing_url = f"{self.base_url}/avoimet-tyopaikat"

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        try:
            resp = await client.get(
                self.listing_url,
                headers={"User-Agent": settings.user_agent},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            links = self._extract_job_links(soup)
            logger.info("Academic Work listing found %d jobs", len(links))
            for url in links:
                try:
                    detail = await self._fetch_detail(client, url)
                    if detail and self._is_tech_role(detail["title"]):
                        results.append(detail)
                except Exception as exc:
                    logger.warning("Academic Work detail fetch failed for %s: %s", url, exc)
        except Exception as exc:
            logger.warning("Academic Work listing fetch failed: %s", exc)
        return results

    def _extract_job_links(self, soup: BeautifulSoup) -> list[str]:
        seen = set()
        links = []
        for a in soup.find_all("a", href=True):
            m = re.match(r"/avoimet-tyopaikat/j/[^/]+/[A-Z0-9]+", a["href"])
            if m:
                full = urljoin(self.base_url, a["href"])
                if full not in seen:
                    seen.add(full)
                    links.append(full)
        return links

    def _is_tech_role(self, title: str) -> bool:
        low = title.lower()
        return any(kw in low for kw in TECH_KEYWORDS)

    async def _fetch_detail(self, client: httpx.AsyncClient, url: str) -> dict | None:
        resp = await client.get(url, headers={"User-Agent": settings.user_agent})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        h1 = soup.find("h1")
        raw_title = html.unescape(h1.get_text(strip=True)) if h1 else ""
        if not raw_title:
            return None

        # Title format is usually "Role, Location" or "Role, Company, Location".
        # Keep the first part as the title and the rest as location/company context.
        parts = [p.strip() for p in raw_title.split(",", 1)]
        if len(parts) == 2:
            title, location = parts
            company = "Academic Work"
        else:
            title = raw_title
            company = "Academic Work"
            location = "Finland"

        body_text = html.unescape(soup.get_text(" ", strip=True))
        salary = extract_salary(body_text)

        source_id = url.rstrip("/").split("/")[-1]
        full_text = f"{title} {body_text}".lower()

        return {
            "source": self.name,
            "source_id": source_id,
            "title": title,
            "company": company,
            "location": location,
            "description": body_text[:3000],
            "url": url,
            "date_posted": datetime.utcnow(),
            "salary_text": salary["text"] if salary else None,
            "salary_min": salary["min"] if salary else None,
            "salary_max": salary["max"] if salary else None,
            "salary_currency": salary["currency"] if salary else None,
            "salary_period": salary["period"] if salary else None,
            "remote": "etätyö" in full_text or "remote" in full_text,
            "hybrid": "hybridi" in full_text or "hybrid" in full_text,
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": [],
        }

    def normalize(self, raw: dict) -> dict:
        return raw

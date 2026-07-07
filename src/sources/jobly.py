import html
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)

# Tech signals used to keep only relevant postings from generic job boards
TECH_KEYWORDS = [
    "software", "developer", "engineer", "data", "it-", "it ", "tech", "programmer",
    "analyst", "cloud", "devops", "security", "web", "mobile", "backend", "frontend",
    "fullstack", "full stack", "ai", "machine learning", "python", "java", "javascript",
    "react", "kotlin", "php", ".net", "azure", "aws", "sap", "consultant", "system",
    "crm", "integration", "embedded", "network", "test", "qa", "support", "administrator",
]


class JoblySource:
    name = "jobly"

    def __init__(self):
        self.base_url = "https://www.jobly.fi"
        self.search_terms = ["developer", "software", "data", "engineer"]

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        seen = set()
        for term in self.search_terms:
            for page in range(2):  # 2 pages × 20 = 40 results per term
                url = f"{self.base_url}/en/jobs?search={term}&page={page}"
                try:
                    resp = await client.get(url, headers={"User-Agent": settings.user_agent})
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                    rows = soup.find_all("article", class_="node-job")
                    logger.info("Jobly term '%s' page %d found %d jobs", term, page, len(rows))
                    for row in rows:
                        parsed = self._parse_row(row)
                        if not parsed:
                            continue
                        if parsed["url"] in seen:
                            continue
                        seen.add(parsed["url"])
                        if self._is_tech_role(parsed["title"]):
                            results.append(parsed)
                except Exception as exc:
                    logger.warning("Jobly search failed for %s page %d: %s", term, page, exc)
                    break
        return results

    def _parse_row(self, row) -> dict | None:
        link = row.find("a", class_="recruiter-job-link", href=True)
        if not link:
            return None

        url = urljoin(self.base_url, link["href"])
        title = html.unescape((link.get("title") or "").strip())
        if not title:
            return None

        # Clean up the visible text: remove "Bookmark job" noise
        text = re.sub(r"\s+", " ", row.get_text(" ", strip=True))
        text = text.replace("Bookmark job", " ")
        text = re.sub(r"\s+", " ", text).strip()

        # Extract date like 06.07.2026
        date_posted = datetime.utcnow()
        date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
        if date_match:
            try:
                date_posted = datetime(
                    int(date_match.group(3)),
                    int(date_match.group(2)),
                    int(date_match.group(1)),
                )
            except ValueError:
                pass

        # Everything after the date is "company location..."
        after_date = text[date_match.end():] if date_match else ""
        after_date = after_date.lstrip(", ").strip()
        parts = [p.strip() for p in after_date.split(",") if p.strip()]
        company = parts[0] if parts else ""
        location = ", ".join(parts[1:]) if len(parts) > 1 else "Finland"

        source_id = url.rstrip("/").split("/")[-1]

        full_text = f"{title} {location}".lower()

        return {
            "source": self.name,
            "source_id": source_id,
            "title": title,
            "company": html.unescape(company),
            "location": html.unescape(location),
            "description": title,
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

    def _is_tech_role(self, title: str) -> bool:
        low = title.lower()
        return any(kw in low for kw in TECH_KEYWORDS)

    def normalize(self, raw: dict) -> dict:
        return raw

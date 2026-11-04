"""Public Finnish startup listings. The legacy /api/jobs endpoint was removed."""
import asyncio
import logging
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scorer import extract_salary

logger = logging.getLogger(__name__)


class TheHubSource:
    name = "thehub"
    max_pages = 12

    @staticmethod
    def _make_url(page: int = 1, limit: int = 50) -> str:
        base = settings.thehub_base_url
        # Migrate the old default without requesting the now-404 API every hour.
        if "/api/jobs" in base:
            base = "https://thehub.io/jobs/location/finland"
        parts = urlsplit(base)
        query = parse_qs(parts.query)
        if page > 1:
            query["page"] = [str(page)]
        else:
            query.pop("page", None)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_listing(html: str) -> tuple[list[dict], bool]:
        soup = BeautifulSoup(html, "html.parser")
        jobs = []
        for link in soup.select("a.card-job-find-list__link[href]"):
            card = link.parent
            title_el = card.select_one(".card-job-find-list__position")
            href = link.get("href", "")
            if not title_el or not href.startswith("/jobs/") or "/location/" in href:
                continue
            title = title_el.get_text(" ", strip=True)
            meta = [span.get_text(" ", strip=True) for span in card.select(".bullet-inline-list > span")]
            if not title:
                continue
            company = meta[0] if meta else ""
            location = meta[1] if len(meta) > 1 else "Finland"
            details = " ".join(meta[2:])
            jobs.append({
                "id": href.rstrip("/").split("/")[-1], "title": title,
                "company": {"name": company}, "location": {"locality": location},
                "description": " — ".join(value for value in (title, company, location, details) if value),
                "absoluteJobUrl": urljoin("https://thehub.io", href),
                "isRemote": "remote" in " ".join(meta).lower(),
            })
        has_next = soup.find("a", attrs={"aria-label": "Go to next page"}) is not None
        return jobs, has_next

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results = []
        seen = set()
        for page in range(1, self.max_pages + 1):
            try:
                response = await client.get(self._make_url(page), headers={"User-Agent": settings.user_agent})
                response.raise_for_status()
                jobs, has_next = self._parse_listing(response.text)
            except Exception:
                if not results:
                    raise  # The orchestrator reports an actual source error, not "empty".
                logger.warning("The Hub stopped after page %d", page - 1, exc_info=True)
                break
            added = 0
            for job in jobs:
                if job["id"] not in seen:
                    seen.add(job["id"])
                    results.append(job)
                    added += 1
            if not has_next or not added:
                break
            await asyncio.sleep(0.25)
        return results

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title") or ""
        description = raw.get("description") or ""
        company = raw.get("company") or {}
        location_data = raw.get("location") or {}
        full_text = f"{title} {description}"
        salary = extract_salary(full_text)
        perks = [perk.get("name") if isinstance(perk, dict) else str(perk)
                 for perk in company.get("perks", []) or []]
        salary_range = raw.get("salaryRange") or {}
        return {
            "source": self.name, "source_id": str(raw.get("id")), "title": title,
            "company": company.get("name") or "", "location": location_data.get("locality") or location_data.get("address") or "",
            "description": description, "url": raw.get("absoluteJobUrl") or f"https://thehub.io/jobs/{raw.get('key')}",
            "date_posted": self._parse_date(raw.get("publishedAt") or raw.get("createdAt")),
            "salary_text": salary["text"] if salary else None,
            "salary_min": salary_range.get("min") if isinstance(salary_range, dict) and salary_range else salary["min"] if salary else None,
            "salary_max": salary_range.get("max") if isinstance(salary_range, dict) and salary_range else salary["max"] if salary else None,
            "salary_currency": salary["currency"] if salary else None, "salary_period": salary["period"] if salary else None,
            "remote": bool(raw.get("isRemote")), "hybrid": "hybrid" in full_text.lower(),
            "company_size": company.get("numberOfEmployees"), "company_founded": company.get("founded"),
            "company_website": company.get("website"), "company_perks": [perk for perk in perks if perk],
        }

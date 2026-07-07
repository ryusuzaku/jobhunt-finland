import logging
from datetime import datetime
from urllib.parse import urlencode

import httpx

from src.config import settings
from src.scorer import extract_salary

logger = logging.getLogger(__name__)


class TheHubSource:
    name = "thehub"

    @staticmethod
    def _make_url(page: int = 1, limit: int = 50) -> str:
        params = {
            "countryCode": "FI",
            "page": page,
            "limit": limit,
        }
        return f"{settings.thehub_base_url}?{urlencode(params)}"

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            # e.g. "2026-06-23T08:51:00.000Z"
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        page = 1
        limit = 50
        while True:
            url = self._make_url(page, limit)
            try:
                resp = await client.get(url, headers={"User-Agent": settings.user_agent})
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("The Hub error page %d: %s", page, exc)
                break

            docs = data.get("docs", [])
            if not docs:
                break

            results.extend(docs)
            total_pages = data.get("pages", 1)
            if page >= total_pages:
                break
            page += 1
            if page > 20:
                break

        logger.info("The Hub fetched %d jobs", len(results))
        return results

    def normalize(self, raw: dict) -> dict:
        title = raw.get("title") or ""
        description = raw.get("description") or ""
        company = raw.get("company") or {}
        company_name = company.get("name") or ""
        location_data = raw.get("location") or {}
        location = location_data.get("locality") or location_data.get("address") or ""
        full_text = f"{title} {description}"
        salary = extract_salary(full_text)

        perks = []
        for perk in company.get("perks", []) or []:
            name = perk.get("name") if isinstance(perk, dict) else str(perk)
            if name:
                perks.append(name)

        return {
            "source": self.name,
            "source_id": str(raw.get("id")),
            "title": title,
            "company": company_name,
            "location": location,
            "description": description,
            "url": raw.get("absoluteJobUrl") or f"https://thehub.io/jobs/{raw.get('key')}",
            "date_posted": self._parse_date(raw.get("publishedAt") or raw.get("createdAt")),
            "salary_text": salary["text"] if salary else None,
            "salary_min": raw.get("salaryRange", {}).get("min") if isinstance(raw.get("salaryRange"), dict) else (salary["min"] if salary else None),
            "salary_max": raw.get("salaryRange", {}).get("max") if isinstance(raw.get("salaryRange"), dict) else (salary["max"] if salary else None),
            "salary_currency": "EUR",
            "salary_period": salary["period"] if salary else None,
            "remote": bool(raw.get("isRemote")),
            "hybrid": "hybrid" in full_text.lower(),
            "company_size": company.get("numberOfEmployees"),
            "company_founded": company.get("founded"),
            "company_website": company.get("website"),
            "company_perks": perks,
        }

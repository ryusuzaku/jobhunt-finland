"""Finnish IT company career-page source.

Reads a curated list of Finnish tech employers from ``data/finnish_companies.json``
and fetches their open roles directly from the company's ATS (Greenhouse,
Teamtailor, SmartRecruiters, Lever, Recruitee, Workable, Ashby, BambooHR).

Each company entry::

    {"name": "Vincit", "career_url": "https://www.vincit.com/careers/",
     "ats": "teamtailor", "slug": "vincitoyj"}

Only jobs in the allowed Finnish dashboard cities are kept, and only tech
roles that look junior-friendly.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from src.config import settings
from src.scorer import extract_salary
from src.sources.india_common import (
    is_junior_friendly,
    keep_role,
    strip_html,
)

logger = logging.getLogger(__name__)


def _allowed_finnish_cities() -> list[str]:
    return [
        loc for loc in settings.allowed_dashboard_locations
        if loc not in ("bengaluru", "bangalore")
    ]


def _is_allowed_location(location: str) -> bool:
    low = (location or "").lower()
    if not low:
        return False
    cities = _allowed_finnish_cities()
    if any(city in low for city in cities):
        return True
    # Keep generic Finland locations; they will be filtered out of the
    # dashboard but are still useful for future pages.
    return "finland" in low


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            # Lever gives milliseconds since epoch.
            return datetime.utcfromtimestamp(value / 1000)
        except (ValueError, OSError):
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class CompanyCareersSource:
    name = "companycareers"

    def __init__(self):
        self.companies = self._load_companies()
        self.headers = {
            "User-Agent": settings.user_agent,
            "Accept": "application/json",
        }
        self.max_concurrent = 5

    def _load_companies(self) -> list[dict]:
        path = Path(settings.company_careers_file)
        if not path.exists():
            logger.warning("Company careers file not found: %s", path)
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to read company careers file: %s", exc)
            return []
        companies = data.get("companies", data) if isinstance(data, dict) else data
        return [c for c in companies if c.get("ats") and c.get("slug")]

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        if not self.companies:
            logger.warning("CompanyCareersSource: no companies configured")
            return []

        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: list[dict] = []

        async def run(company: dict):
            async with semaphore:
                try:
                    jobs = await self._fetch_company(client, company)
                    results.extend(jobs)
                    if jobs:
                        logger.info(
                            "companycareers: %s contributed %d jobs",
                            company.get("name"), len(jobs),
                        )
                except Exception as exc:
                    logger.warning(
                        "companycareers: %s failed: %s", company.get("name"), exc
                    )
                await asyncio.sleep(0.3)

        await asyncio.gather(*(run(c) for c in self.companies))
        logger.info("companycareers fetched %d jobs total", len(results))
        return results

    async def _fetch_company(self, client: httpx.AsyncClient, company: dict) -> list[dict]:
        ats = (company.get("ats") or "").lower()
        slug = company.get("slug") or ""
        if ats == "greenhouse":
            return await self._fetch_greenhouse(client, company, slug)
        if ats == "teamtailor":
            return await self._fetch_teamtailor(client, company, slug)
        if ats == "smartrecruiters":
            return await self._fetch_smartrecruiters(client, company, slug)
        if ats == "lever":
            return await self._fetch_lever(client, company, slug)
        if ats == "recruitee":
            return await self._fetch_recruitee(client, company, slug)
        if ats == "workable":
            return await self._fetch_workable(client, company, slug)
        if ats == "ashby":
            return await self._fetch_ashby(client, company, slug)
        if ats == "bamboohr":
            return await self._fetch_bamboohr(client, company, slug)
        logger.warning("companycareers: unsupported ats '%s' for %s", ats, company.get("name"))
        return []

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    def _keep(self, company: dict, title: str, location: str, description: str) -> bool:
        if not title:
            return False
        if not _is_allowed_location(location):
            return False
        # Profile-aware: IT employers also post marketing/finance/design roles.
        if not keep_role(title, description, getattr(self, "active_profiles", None)):
            return False
        if not is_junior_friendly(title):
            return False
        return True

    def _build_job(
        self,
        company: dict,
        job_id: str,
        title: str,
        location: str,
        url: str,
        description: str,
        date_posted,
        remote_hint: str = "",
    ) -> dict:
        description_text = strip_html(description) if "<" in (description or "") else (description or "")
        full_text = f"{title} {description_text} {location} {remote_hint}".lower()
        salary = extract_salary(f"{title} {description_text}")
        return {
            "source": self.name,
            "source_id": f"{company.get('slug')}-{job_id}",
            "title": title,
            "company": company.get("name") or "",
            "location": location,
            "description": description_text or f"{title} at {company.get('name')}",
            "url": url or company.get("career_url") or "",
            "date_posted": _parse_date(date_posted),
            "salary_text": salary["text"] if salary else None,
            "salary_min": salary["min"] if salary else None,
            "salary_max": salary["max"] if salary else None,
            "salary_currency": salary["currency"] if salary else None,
            "salary_period": salary["period"] if salary else None,
            "remote": "remote" in full_text or "etä" in full_text,
            "hybrid": "hybrid" in full_text or "hybridi" in full_text,
            "company_size": None,
            "company_founded": None,
            "company_website": company.get("career_url"),
            "company_perks": [],
        }

    # ------------------------------------------------------------------
    # ATS adapters
    # ------------------------------------------------------------------

    async def _fetch_greenhouse(self, client, company, slug) -> list[dict]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title") or ""
            location = (item.get("location") or {}).get("name") or ""
            description = item.get("content") or ""
            if not self._keep(company, title, location, description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id")),
                    title,
                    location,
                    item.get("absolute_url") or "",
                    description,
                    item.get("updated_at"),
                )
            )
        return jobs

    async def _fetch_teamtailor(self, client, company, slug) -> list[dict]:
        url = f"https://{slug}.teamtailor.com/jobs.json"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("items", []):
            title = item.get("title") or ""
            posting = item.get("_jobposting") or {}
            locations = []
            for loc in posting.get("jobLocation") or []:
                address = (loc or {}).get("address") or {}
                locality = address.get("addressLocality")
                if locality:
                    locations.append(locality)
            location = ", ".join(locations)
            description = item.get("content_html") or ""
            if not self._keep(company, title, location, description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id") or (item.get("url") or "").rstrip("/").split("/")[-1]),
                    title,
                    location,
                    item.get("url") or "",
                    description,
                    item.get("date_published"),
                )
            )
        return jobs

    async def _fetch_smartrecruiters(self, client, company, slug) -> list[dict]:
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("content", []):
            title = item.get("name") or ""
            loc = item.get("location") or {}
            location = loc.get("fullLocation") or loc.get("city") or ""
            remote_hint = "remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else "")
            description = " ".join(
                filter(
                    None,
                    [
                        (item.get("function") or {}).get("label") or "",
                        (item.get("experienceLevel") or {}).get("label") or "",
                        (item.get("industry") or {}).get("label") or "",
                    ],
                )
            )
            if not self._keep(company, title, location, description):
                continue
            job_id = str(item.get("id") or item.get("uuid"))
            apply_url = (
                f"https://jobs.smartrecruiters.com/{company.get('slug')}/{job_id}"
            )
            jobs.append(
                self._build_job(
                    company,
                    job_id,
                    title,
                    location,
                    apply_url,
                    description or title,
                    item.get("releasedDate"),
                    remote_hint=remote_hint,
                )
            )
        return jobs

    async def _fetch_lever(self, client, company, slug) -> list[dict]:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data or []:
            title = item.get("text") or ""
            categories = item.get("categories") or {}
            location = categories.get("location") or ""
            description = item.get("descriptionPlain") or ""
            if not self._keep(company, title, location, description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id")),
                    title,
                    location,
                    item.get("hostedUrl") or "",
                    description,
                    item.get("createdAt"),
                )
            )
        return jobs

    async def _fetch_recruitee(self, client, company, slug) -> list[dict]:
        url = f"https://{slug}.recruitee.com/api/v2/offers"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        offers = data.get("offers", data) if isinstance(data, dict) else data
        jobs = []
        for item in offers or []:
            title = item.get("title") or ""
            location = item.get("location") or item.get("city") or ""
            description = item.get("description") or ""
            if not self._keep(company, title, location, description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id") or item.get("slug")),
                    title,
                    location,
                    item.get("careers_url") or item.get("url") or "",
                    description,
                    item.get("published_at") or item.get("created_at"),
                )
            )
        return jobs

    async def _fetch_workable(self, client, company, slug) -> list[dict]:
        url = f"https://careers-page.workable.com/api/v1/accounts/{slug}?details=true"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        jobs_data = data.get("results") or data.get("jobs") or []
        jobs = []
        for item in jobs_data:
            title = item.get("title") or ""
            loc = item.get("location") or {}
            location = ", ".join(
                filter(None, [loc.get("city"), loc.get("country")])
            ) if isinstance(loc, dict) else str(loc or "")
            description = item.get("description") or ""
            if not self._keep(company, title, location, description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id") or item.get("shortcode")),
                    title,
                    location,
                    item.get("url") or "",
                    description,
                    item.get("created_at") or item.get("published_at"),
                )
            )
        return jobs

    async def _fetch_ashby(self, client, company, slug) -> list[dict]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("jobs", []):
            title = item.get("title") or ""
            location = item.get("location") or ""
            description = item.get("descriptionPlain") or ""
            if not self._keep(company, title, location, description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id")),
                    title,
                    location,
                    item.get("jobUrl") or "",
                    description,
                    item.get("publishedAt"),
                )
            )
        return jobs

    async def _fetch_bamboohr(self, client, company, slug) -> list[dict]:
        url = f"https://{slug}.bamboohr.com/careers/list"
        resp = await client.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("result", data) if isinstance(data, dict) else data
        jobs = []
        for item in rows or []:
            title = item.get("jobOpeningName") or item.get("title") or ""
            location = item.get("location") or ""
            if isinstance(location, dict):
                location = location.get("city") or ""
            description = item.get("description") or ""
            if not self._keep(company, title, str(location), description):
                continue
            jobs.append(
                self._build_job(
                    company,
                    str(item.get("id")),
                    title,
                    str(location),
                    item.get("url") or "",
                    description,
                    item.get("datePosted") or item.get("created"),
                )
            )
        return jobs

    def normalize(self, raw: dict) -> dict:
        return raw

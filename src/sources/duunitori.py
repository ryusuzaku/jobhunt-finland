import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from src.config import settings
from src.job_profiles import fi_search_terms
from src.scorer import extract_salary

logger = logging.getLogger(__name__)

# Senior-only signals: drop the posting if the heading contains these and
# no junior/entry signal is present. This keeps Duunitori's volume manageable
# for a junior-focused search.
SENIOR_ONLY_KEYWORDS = [
    "senior", "lead", "principal", "staff", "manager", "head of",
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "vahva kokemus", "erityisasiantuntija", "projektipäällikkö",
]
JUNIOR_SIGNALS = [
    "junior", "trainee", "harjoittelu", "harjoittelija", "graduate",
    "entry-level", "entry level", "alin", "assistentti", "opiskelija",
]


def _is_likely_junior_friendly(heading: str) -> bool:
    low = heading.lower()
    has_junior_signal = any(sig in low for sig in JUNIOR_SIGNALS)
    has_senior_only = any(kw in low for kw in SENIOR_ONLY_KEYWORDS)
    # Keep if it has a junior signal, or if it lacks explicit senior-only signals
    return has_junior_signal or not has_senior_only


class DuunitoriSource:
    name = "duunitori"

    @staticmethod
    def _make_url(term: str, page: int = 1) -> str:
        params = {
            "search": term,
            "search_also_descr": 1,
            "format": "json",
            "page": page,
        }
        return f"{settings.duunitori_base_url}?{urlencode(params)}"

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

    def _within_age_cutoff(self, date: datetime | None) -> bool:
        if not date:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.duunitori_max_age_days)
        # date may be offset-aware; ensure cutoff is offset-aware
        return date >= cutoff

    async def fetch(self, client: httpx.AsyncClient) -> list[dict]:
        results: list[dict] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.duunitori_max_age_days)

        # Profile-aware terms; falls back to settings.search_terms when empty.
        for term in fi_search_terms(getattr(self, "active_profiles", None)):
            page = 1
            while True:
                if page > settings.duunitori_max_pages_per_term:
                    break

                url = self._make_url(term, page)
                try:
                    resp = await client.get(url, headers={"User-Agent": settings.user_agent})
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPStatusError as exc:
                    logger.warning("Duunitori HTTP error for '%s' page %d: %s", term, page, exc.response.status_code)
                    break
                except Exception as exc:
                    logger.warning("Duunitori error for '%s' page %d: %s", term, page, exc)
                    break

                page_results = data.get("results", [])
                if not page_results:
                    break

                # Stop paginating this term once the oldest result is beyond the cutoff.
                # Results are roughly newest-first, so this keeps volume in check.
                oldest = min(
                    (self._parse_date(r.get("date_posted")) for r in page_results),
                    default=None,
                )
                if oldest and oldest < cutoff:
                    # Still keep the in-cutoff rows from this page, then stop.
                    page_results = [
                        r for r in page_results
                        if self._within_age_cutoff(self._parse_date(r.get("date_posted")))
                    ]
                    if page_results:
                        results.extend(page_results)
                    break

                results.extend(page_results)

                if not data.get("next"):
                    break
                page += 1

        seen = set()
        unique: list[dict] = []
        dropped_senior = 0
        for raw in results:
            slug = raw.get("slug")
            if not slug or slug in seen:
                continue
            heading = raw.get("heading") or ""
            if not _is_likely_junior_friendly(heading):
                dropped_senior += 1
                continue
            seen.add(slug)
            unique.append(raw)

        logger.info(
            "Duunitori fetched %d unique jobs (dropped %d senior-only titles)",
            len(unique),
            dropped_senior,
        )
        return unique

    def normalize(self, raw: dict) -> dict:
        title = raw.get("heading") or ""
        location = raw.get("municipality_name") or ""
        description = raw.get("descr") or ""
        full_text = f"{title} {description}"
        salary = extract_salary(full_text)

        return {
            "source": self.name,
            "source_id": raw.get("slug"),
            "title": title,
            "company": raw.get("company_name") or "",
            "location": location,
            "description": description,
            "url": f"https://duunitori.fi/tyopaikat/tyo/{raw.get('slug')}",
            "date_posted": self._parse_date(raw.get("date_posted")),
            "salary_text": salary["text"] if salary else None,
            "salary_min": salary["min"] if salary else None,
            "salary_max": salary["max"] if salary else None,
            "salary_currency": salary["currency"] if salary else None,
            "salary_period": salary["period"] if salary else None,
            "remote": "remote" in full_text.lower() or "etä" in full_text.lower(),
            "hybrid": "hybrid" in full_text.lower() or "hybridi" in full_text.lower(),
            "company_size": None,
            "company_founded": None,
            "company_website": None,
            "company_perks": [],
        }

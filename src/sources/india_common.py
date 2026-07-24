"""Shared helpers for Indian job-board sources.

Filtering goals:
- Bengaluru/Bangalore only (matches the existing /bengaluru page).
- Tech roles only.
- Junior-friendly: drop explicit senior/lead/manager/5+ years titles unless a
  junior signal is present.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

TECH_KEYWORDS = [
    "software", "developer", "engineer", "data", "devops", "cloud",
    "frontend", "backend", "full stack", "fullstack", "full-stack", "web",
    "mobile", "python", "javascript", "typescript", "react", "node", "java",
    "kotlin", "ai", "machine learning", "ml", "analytics", "security", "qa",
    "test", "sysadmin", "database", "sql", "aws", "azure", "gcp", "sre",
]

NON_TECH_KEYWORDS = [
    "sales", "business development", "bpo", "call center", "telecaller",
    "customer support", "customer service", "recruiter", "hr ", "human resource",
    "marketing", "content writer", "accountant", "finance", "operations",
    "teacher", "nurse", "pharmacist", "receptionist", "delivery",
]

SENIOR_ONLY_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "principal", "staff", "manager",
    "head of", "architect", "director", "vp ", "vice president",
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
]

JUNIOR_SIGNALS = [
    "junior", "jr.", "jr ", "trainee", "intern", "internship", "fresher",
    "freshers", "graduate", "entry-level", "entry level", "0-1", "0-2",
    "0 to 1", "0 to 2", "no experience", "early career",
]

BENGALURU_TOKENS = ["bengaluru", "bangalore"]

# Staffing-agency / consultancy repost signals. Indian boards are full of
# agencies reposting their clients' roles ("XYZ Manpower Hiring For ..."),
# which adds noise and dead-end apply links.
AGENCY_SPAM_KEYWORDS = [
    "hiring for",
    "manpower",
    "placement",
    "staffing",
    "walkin",
    "walk-in",
    "walk in",
    "recruitment",
    "recruiting services",
]


from src.job_profiles import keep_job, selected_profiles

_TECH_GROUP_NOTE = "Tech roles only (default); profile-aware when profiles are selected."


def keep_role(title: str, extra_text: str = "", profiles: list[str] | None = None) -> bool:
    """Profile-aware replacement for is_tech_role.

    When job profiles are selected, keep_job decides and the NON_TECH
    drop-list no longer applies (the user explicitly asked for e.g.
    marketing jobs). With no selection, legacy tech-only behavior.
    """
    if selected_profiles(profiles):
        return keep_job(title, extra_text, profiles)
    return is_tech_role(title, extra_text)


def is_agency_spam(company: str, title: str = "") -> bool:
    low = f"{company} {title}".lower()
    return any(kw in low for kw in AGENCY_SPAM_KEYWORDS)

_RELATIVE_DATE_RE = re.compile(
    r"(\d+|few|a|an)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
    re.IGNORECASE,
)

_UNIT_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
    "year": 365 * 86400,
}


def is_bengaluru_location(location: str) -> bool:
    low = (location or "").lower()
    return any(tok in low for tok in BENGALURU_TOKENS)


def is_tech_role(title: str, extra_text: str = "") -> bool:
    combined = f"{title} {extra_text}".lower()
    if any(kw in combined for kw in NON_TECH_KEYWORDS):
        # A tech word in the title still wins over a stray non-tech word in
        # the description (e.g. "Sales Engineer" is dropped, but a backend
        # role mentioning "sales team" is kept).
        title_low = title.lower()
        if any(kw in title_low for kw in TECH_KEYWORDS):
            return True
        return False
    title_low = title.lower()
    return any(kw in title_low for kw in TECH_KEYWORDS)


def is_junior_friendly(title: str, extra_text: str = "") -> bool:
    title_low = title.lower()
    # A junior signal in the title always wins.
    if any(sig in title_low for sig in JUNIOR_SIGNALS):
        return True
    # Senior-only wording anywhere (title or experience) drops the job.
    combined = f"{title} {extra_text}".lower()
    return not any(kw in combined for kw in SENIOR_ONLY_KEYWORDS)


def parse_relative_date(text: str | None) -> datetime | None:
    """Parse strings like 'posted 1 day ago' / '3 weeks ago' / 'Few hours ago'."""
    if not text:
        return None
    m = _RELATIVE_DATE_RE.search(text)
    if not m:
        return None
    amount_raw, unit = m.group(1).lower(), m.group(2).lower()
    if amount_raw in ("a", "an"):
        amount = 1
    elif amount_raw == "few":
        amount = 3
    else:
        try:
            amount = int(amount_raw)
        except ValueError:
            return None
    seconds = amount * _UNIT_SECONDS.get(unit, 0)
    if not seconds:
        return None
    return datetime.utcnow() - timedelta(seconds=seconds)


def strip_html(html_text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html_text or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&#39;|&rsquo;|&lsquo;", "'", text)
    text = re.sub(r"&quot;|&ldquo;|&rdquo;", '"', text)
    text = re.sub(r"&mdash;|&ndash;", "-", text)
    return re.sub(r"\s+", " ", text).strip()

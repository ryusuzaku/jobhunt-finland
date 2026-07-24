import re
from src.config import settings
from src.job_profiles import JOB_PROFILES, keyword_pattern

# Backward-compatible alias (was defined here before job_profiles.py).
ROLE_TRACKS = JOB_PROFILES

# Signals that suggest strong learning/growth opportunity for juniors
LEARNING_POSITIVE = [
    "mentor", "mentoring", "mentorship", "coach", "coaching",
    "trainee", "training", "intern", "internship", "harjoittelu", "harjoittelija",
    "junior", "entry-level", "entry level", "graduate", "graduates",
    "learn", "learning", "grow", "growth", "career development",
    "personal development", "professional development", "upskill",
    "koulutus", "kouluttaa", "kehitys", "kehittää", "osaaminen",
]

# Signals that suggest good work-life / location fit
WORKLIFE_POSITIVE = [
    "remote", "etätyö", "etä", "hybrid", "hybridi",
    "flexible", "joustava", "work-life balance", "work life balance",
    "työhyvinvointi", "wellbeing", "well-being",
    "sairausvakuutus", "lounas", "liikunta", "kuntosali",
]

# Seniority signals that should REDUCE the score for a junior search
SENIOR_NEGATIVE = [
    "senior", "lead", "principal", "staff", "manager", "head of",
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "extensive experience", "years of experience", "vahva kokemus",
    "vaativa", "erityisasiantuntija",
]

# Perks that suggest a good workplace (used for company score)
GOOD_PERKS = [
    "remote work", "flexible", "paid holiday", "parental leave", "maternity",
    "paternity", "health", "insurance", "wellbeing", "lunch", "sport", "gym",
    "pension", "bonus", "equity", "stock", "learning", "conference",
]

# How strongly each experience level penalizes senior-looking roles.
EXPERIENCE_PENALTY_FACTOR = {
    "student": 1.3,
    "graduate": 1.15,
    "junior": 1.0,
    "mid": 0.6,
}


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s\+#.]", " ", text.lower())


def _count_matches(text: str, keywords: list[str]) -> int:
    norm = _normalize(text)
    total = 0
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        total += len(re.findall(pattern, norm))
    return total


def extract_salary(text: str) -> dict | None:
    """
    Extract salary information from text.
    Returns dict with min, max, currency, period, text or None.
    """
    if not text:
        return None

    text = text.replace("\xa0", " ").replace(" ", " ")

    # --- Indian formats (checked first so they win on Indian job boards) ---
    inr = _extract_inr_salary(text)
    if inr:
        return inr

    text = text.replace(",", "")

    # Patterns:
    # 3000-4000 €/kk
    # 3000 € - 4000 €
    # 15-20 €/h
    # 50000-60000 €/vuosi
    patterns = [
        # Range with slash period: 3000-4000 €/kk
        r"(\d{3,6})\s*[-–]\s*(\d{3,6})\s*€\s*/?\s*(kk|h|v|vuosi|vuodessa|month|hour|year)",
        # Range separated: 3000 € - 4000 €/kk
        r"(\d{3,6})\s*€\s*[-–]\s*(\d{3,6})\s*€\s*/?\s*(kk|h|v|vuosi|vuodessa|month|hour|year)?",
        # Single: 3500 €/kk
        r"(\d{3,6})\s*€\s*/?\s*(kk|h|v|vuosi|vuodessa|month|hour|year)",
        # Monthly salary words: 3500 € per month
        r"(\d{3,6})\s*€\s*(per\s*month|per\s*hour|per\s*year|monthly|hourly|annually)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = m.groups()
            if len(groups) >= 3 and groups[2]:
                min_val = float(groups[0])
                max_val = float(groups[1])
                period = _normalize_period(groups[2])
            elif len(groups) == 2:
                min_val = float(groups[0])
                max_val = float(groups[0])
                period = _normalize_period(groups[1])
            else:
                continue

            return {
                "min": min_val,
                "max": max_val,
                "currency": "EUR",
                "period": period,
                "text": m.group(0),
            }
    return None


def _extract_inr_salary(text: str) -> dict | None:
    """Extract Indian salary formats: '4.0 - 8 LPA', '₹3,00,000 - 5,00,000 /year',
    '₹ 15,000 /month', '₹ 5,000 lump sum'."""

    # LPA range: 4.0 - 8 LPA  /  4-8 LPA  /  1.8 LPA - 11.7 LPA
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:LPA|lakhs?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*LPA",
        text,
        re.IGNORECASE,
    ) or re.search(
        r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*LPA",
        text,
        re.IGNORECASE,
    )
    if m:
        min_val = float(m.group(1)) * 100000
        max_val = float(m.group(2)) * 100000
        return {
            "min": min_val,
            "max": max_val,
            "currency": "INR",
            "period": "year",
            "text": m.group(0),
        }

    # Rupee range: ₹3,00,000 - 5,00,000 /year  (or ₹ 3-5 LPA handled above)
    m = re.search(
        r"₹\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*₹?\s*([\d,]+(?:\.\d+)?)\s*/?\s*(year|yr|annum|annual|month|mo|lump\s*sum|lumpsum)?",
        text,
        re.IGNORECASE,
    )
    if m:
        min_val = float(m.group(1).replace(",", ""))
        max_val = float(m.group(2).replace(",", ""))
        period = _normalize_inr_period(m.group(3))
        # Heuristic: small numbers without a period are likely LPA.
        if not m.group(3) and max_val <= 100:
            min_val *= 100000
            max_val *= 100000
            period = "year"
        return {
            "min": min_val,
            "max": max_val,
            "currency": "INR",
            "period": period,
            "text": m.group(0),
        }

    # Single rupee amount: ₹ 15,000 /month
    m = re.search(
        r"₹\s*([\d,]+(?:\.\d+)?)\s*/?\s*(year|yr|annum|annual|month|mo|lump\s*sum|lumpsum)",
        text,
        re.IGNORECASE,
    )
    if m:
        val = float(m.group(1).replace(",", ""))
        return {
            "min": val,
            "max": val,
            "currency": "INR",
            "period": _normalize_inr_period(m.group(2)),
            "text": m.group(0),
        }
    return None


def _normalize_inr_period(period: str | None) -> str:
    if not period:
        return "year"
    p = period.lower().strip()
    if p in ("month", "mo"):
        return "month"
    if p in ("lump sum", "lumpsum"):
        return "lump"
    return "year"


def _normalize_period(period: str) -> str:
    p = period.lower().strip()
    if p in ("kk", "month", "monthly", "per month"):
        return "month"
    if p in ("h", "hour", "hourly", "per hour"):
        return "hour"
    if p in ("v", "vuosi", "vuodessa", "year", "yearly", "annually", "per year"):
        return "year"
    return p


def score_job(
    title: str,
    description: str,
    location: str,
    prefs: dict,
    remote: bool = False,
    hybrid: bool = False,
    company_size: str | None = None,
    company_founded: str | None = None,
    company_perks: list[str] | None = None,
) -> dict:
    """
    Heuristic scoring for a junior tech job.
    Returns sub-scores and an overall score (0-100).
    """
    full_text = f"{title} {description} {location}"
    norm_text = _normalize(full_text)

    # Learning score (0-100)
    learn_matches = _count_matches(full_text, LEARNING_POSITIVE)
    learning_score = min(100, learn_matches * 20)

    # Work-life / location score (0-100)
    wl_matches = _count_matches(full_text, WORKLIFE_POSITIVE)
    location_bonus = 0
    preferred_locs = [loc.lower() for loc in prefs.get("preferred_locations", settings.default_preferred_locations)]
    if any(loc in location.lower() for loc in preferred_locs):
        location_bonus = 25
    if prefs.get("remote_ok", settings.default_remote_ok) and (remote or "remote" in norm_text or "etä" in norm_text):
        location_bonus += 25
    if prefs.get("hybrid_ok", settings.default_hybrid_ok) and (hybrid or "hybrid" in norm_text or "hybridi" in norm_text):
        location_bonus += 15
    worklife_score = min(100, wl_matches * 15 + location_bonus)

    # Tech stack score (0-100)
    preferred_tech = [t.lower() for t in prefs.get("preferred_tech", settings.default_preferred_tech)]
    tech_matches = 0
    for tech in preferred_tech:
        pattern = r"\b" + re.escape(tech) + r"\b"
        if re.search(pattern, norm_text):
            tech_matches += 1
    tech_score = min(100, tech_matches * 15)

    # Company score (0-100)
    company_score = 0
    if company_perks:
        perk_text = " ".join(company_perks).lower()
        good_matches = sum(1 for p in GOOD_PERKS if p in perk_text)
        company_score += min(60, good_matches * 10)
    # Slight bonus for small/medium startups (often better for juniors)
    if company_size and company_size in {"1-10", "11-50", "51-100"}:
        company_score += 20
    elif company_size and company_size in {"101-200"}:
        company_score += 10
    # Slight bonus for established but not ancient companies
    if company_founded:
        try:
            year = int(company_founded)
            if 2010 <= year <= 2024:
                company_score += 10
            elif year >= 2000:
                company_score += 5
        except ValueError:
            pass
    company_score = min(100, company_score)

    # Seniority penalty (0-60, subtracted from final), scaled by the
    # user's experience level (students feel senior roles harder).
    senior_matches = _count_matches(full_text, SENIOR_NEGATIVE)
    level = prefs.get("experience_level", "junior")
    penalty_factor = EXPERIENCE_PENALTY_FACTOR.get(level, 1.0)
    penalty = min(60, senior_matches * 15 * penalty_factor)

    # Profile/track bonus (additive; only when the user picked profiles,
    # so default behaviour is unchanged). Title matches count double.
    track_bonus = 0
    chosen_tracks = prefs.get("job_profiles") or prefs.get("role_tracks") or []
    if chosen_tracks:
        title_norm = _normalize(title)
        track_hits = 0
        for track in chosen_tracks:
            info = JOB_PROFILES.get(track)
            if not info:
                continue
            for kw in info["title_keywords"]:
                pattern = keyword_pattern(kw)
                if re.search(pattern, norm_text):
                    track_hits += 1
                    if re.search(pattern, title_norm):
                        track_hits += 1  # title match counts double
                    break  # one hit per profile is enough
        track_bonus = min(15, track_hits * 6)

    # Weighted final score
    weighted = (
        learning_score * settings.weight_learning
        + worklife_score * settings.weight_worklife
        + tech_score * settings.weight_tech
        + company_score * settings.weight_company
    )
    final = max(0, min(100, weighted - penalty + track_bonus))

    return {
        "score": round(final, 1),
        "learning_score": round(learning_score, 1),
        "worklife_score": round(worklife_score, 1),
        "tech_score": round(tech_score, 1),
        "company_score": round(company_score, 1),
    }

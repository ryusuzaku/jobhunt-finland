import re
from src.config import settings

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

    text = text.replace("\xa0", " ").replace(",", "").replace(" ", " ")

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

    # Seniority penalty (0-60, subtracted from final)
    senior_matches = _count_matches(full_text, SENIOR_NEGATIVE)
    penalty = min(60, senior_matches * 15)

    # Weighted final score
    weighted = (
        learning_score * settings.weight_learning
        + worklife_score * settings.weight_worklife
        + tech_score * settings.weight_tech
        + company_score * settings.weight_company
    )
    final = max(0, min(100, weighted - penalty))

    return {
        "score": round(final, 1),
        "learning_score": round(learning_score, 1),
        "worklife_score": round(worklife_score, 1),
        "tech_score": round(tech_score, 1),
        "company_score": round(company_score, 1),
    }

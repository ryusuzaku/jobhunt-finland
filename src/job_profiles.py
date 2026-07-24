"""Job profiles: the registry that makes JobHunt usable beyond IT.

Each profile bundles the keywords that identify matching jobs, the search
terms used by query-driven sources, and the skill presets shown in
onboarding. Selecting profiles in onboarding adapts fetching, filtering,
and scoring; an empty selection keeps the original tech-only behavior.

Profile keys for the Tech group are identical to the legacy ROLE_TRACKS
keys, so existing `role_tracks` preferences keep working.
"""

import re

from src.config import settings

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

JOB_PROFILES: dict[str, dict] = {
    # ---- Tech (keys match legacy ROLE_TRACKS) ----
    "software": {
        "label": "Software / Backend", "icon": "💻", "group": "Tech",
        "title_keywords": ["software", "backend", "back-end", "full stack", "full-stack",
                            "fullstack", "api developer", "server", "embedded"],
        "terms_fi": ["junior developer", "ohjelmistokehittäjä", "software developer", "backend developer"],
        "terms_en": ["software developer", "backend developer", "full stack developer"],
        "terms_in": ["software developer", "backend developer", "full stack developer"],
        "skill_presets": ["python", "java", "c#", "go", "sql", "git", "docker", "rest api"],
        "match_description": True,
    },
    "frontend": {
        "label": "Frontend / Web", "icon": "🎨", "group": "Tech",
        "title_keywords": ["frontend", "front-end", "web developer", "web development",
                            "react", "vue", "angular", "typescript", "javascript", "css"],
        "terms_fi": ["frontend developer", "web developer"],
        "terms_en": ["frontend developer", "web developer", "react developer"],
        "terms_in": ["frontend developer", "react developer"],
        "skill_presets": ["javascript", "typescript", "react", "vue", "angular", "html", "css", "tailwind"],
        "match_description": True,
    },
    "data": {
        "label": "Data / AI / ML", "icon": "🤖", "group": "Tech",
        "title_keywords": ["data engineer", "data scientist", "machine learning", "ml engineer",
                            "ai engineer", "analytics", "etl", "data analyst", "data platform",
                            "deep learning", "nlp", "data"],
        "terms_fi": ["data engineer", "data analyst", "data-analyytikko", "machine learning engineer"],
        "terms_en": ["data analyst", "data engineer", "machine learning engineer"],
        "terms_in": ["data analyst", "data engineer", "machine learning engineer"],
        "skill_presets": ["python", "sql", "pandas", "tensorflow", "pytorch", "spark", "power bi", "excel"],
        "match_description": True,
    },
    "devops": {
        "label": "DevOps / Cloud", "icon": "☁️", "group": "Tech",
        "title_keywords": ["devops", "cloud", "infrastructure", "kubernetes", "docker",
                            "aws", "azure", "gcp", "sre", "platform engineer", "ci/cd", "terraform"],
        "terms_fi": ["devops engineer", "cloud engineer"],
        "terms_en": ["devops engineer", "cloud engineer"],
        "terms_in": ["devops engineer", "cloud engineer"],
        "skill_presets": ["aws", "azure", "gcp", "docker", "kubernetes", "terraform", "linux", "ci/cd"],
        "match_description": True,
    },
    "mobile": {
        "label": "Mobile", "icon": "📱", "group": "Tech",
        "title_keywords": ["android", "ios", "mobile", "kotlin", "swift", "flutter", "react native"],
        "terms_fi": ["mobile developer", "android developer", "ios developer"],
        "terms_en": ["android developer", "ios developer", "mobile developer"],
        "terms_in": ["android developer", "ios developer", "flutter developer"],
        "skill_presets": ["kotlin", "swift", "flutter", "react native", "android", "ios", "firebase"],
        "match_description": True,
    },
    "qa": {
        "label": "QA / Testing", "icon": "🧪", "group": "Tech",
        "title_keywords": ["qa", "test engineer", "testing", "quality assurance",
                            "test automation", "sdet"],
        "terms_fi": ["test automation engineer", "qa engineer", "testaus"],
        "terms_en": ["qa engineer", "test automation engineer"],
        "terms_in": ["qa engineer", "test automation engineer"],
        "skill_presets": ["selenium", "cypress", "playwright", "junit", "test automation", "sql"],
        "match_description": True,
    },
    "security": {
        "label": "Security", "icon": "🔒", "group": "Tech",
        "title_keywords": ["security", "infosec", "cybersecurity", "cyber security",
                            "pentest", "secops", "soc analyst"],
        "terms_fi": ["security engineer", "tietoturva"],
        "terms_en": ["security engineer", "cybersecurity analyst"],
        "terms_in": ["security engineer", "soc analyst"],
        "skill_presets": ["networking", "linux", "siem", "penetration testing", "cryptography"],
        "match_description": True,
    },

    # ---- Design ----
    "design": {
        "label": "Design / UX", "icon": "✏️", "group": "Design",
        "title_keywords": ["designer", "ux", "ui design", "product design", "figma",
                            "user experience", "muotoilija", "graafinen"],
        "terms_fi": ["ux designer", "ui designer", "muotoilija", "product designer"],
        "terms_en": ["ux designer", "product designer", "ui designer"],
        "terms_in": ["ui ux designer", "ux designer", "graphic designer"],
        "skill_presets": ["figma", "sketch", "adobe xd", "prototyping", "design systems", "user research"],
        "match_description": True,
    },

    # ---- Business ----
    "marketing": {
        "label": "Marketing", "icon": "📣", "group": "Business",
        "title_keywords": ["marketing", "markkinoin*", "viestin*", "sisällön*",
                            "content", "seo", "growth", "brand", "bränd*", "social media",
                            "digital marketing", "copywriter", "communications"],
        "terms_fi": ["markkinointi", "viestintä", "sisällöntuotanto", "digital marketing"],
        "terms_en": ["marketing", "digital marketing", "content marketing", "seo specialist"],
        "terms_in": ["digital marketing", "marketing executive", "content writer", "seo"],
        "skill_presets": ["seo", "google analytics", "hubspot", "content", "social media",
                           "copywriting", "meta ads", "mailchimp"],
        "match_description": False,
    },
    "sales": {
        "label": "Sales", "icon": "💼", "group": "Business",
        "title_keywords": ["sales", "myyn*", "account manager", "business development",
                            "account executive", "customer success", "key account",
                            "sales representative", "myyntipäällikkö"],
        "terms_fi": ["myynti", "sales", "account manager"],
        "terms_en": ["sales", "account manager", "business development"],
        "terms_in": ["sales executive", "business development executive", "inside sales"],
        "skill_presets": ["crm", "salesforce", "hubspot", "negotiation", "cold calling", "excel"],
        "match_description": False,
    },
    "finance": {
        "label": "Finance & Accounting", "icon": "📊", "group": "Business",
        "title_keywords": ["finance", "accounting", "kirjanpi*", "accountant", "controller",
                            "bookkeeping", "payroll", "palkanlask*", "financial analyst",
                            "talousasiantunti*", "audit", "kirjanpitäjä"],
        "terms_fi": ["kirjanpitäjä", "controller", "financial analyst", "talousasiantuntija"],
        "terms_en": ["accountant", "financial analyst", "controller", "finance"],
        "terms_in": ["accountant", "finance executive", "financial analyst"],
        "skill_presets": ["excel", "accounting", "sap", "bookkeeping", "quickbooks", "financial modeling"],
        "match_description": False,
    },
    "hr": {
        "label": "HR & Recruiting", "icon": "🧑‍🤝‍🧑", "group": "Business",
        "title_keywords": ["human resources", "henkilöstö*", "recruiter", "recruitment",
                            "rekry*", "talent acquisition", "people partner",
                            "hr assistant", "hr coordinator", "hr specialist"],
        "terms_fi": ["henkilöstö", "hr", "rekrytointi"],
        "terms_en": ["hr", "recruiter", "talent acquisition"],
        "terms_in": ["hr recruiter", "hr executive", "talent acquisition"],
        "skill_presets": ["recruiting", "onboarding", "hr systems", "linkedin recruiter",
                           "excel", "communication"],
        "match_description": False,
    },
    "customer_service": {
        "label": "Customer Service", "icon": "🎧", "group": "Business",
        "title_keywords": ["customer service", "customer support", "asiakaspalvel*", "helpdesk",
                            "service desk", "asiakastu*", "call center", "support specialist",
                            "customer care"],
        "terms_fi": ["asiakaspalvelu", "customer service", "helpdesk"],
        "terms_en": ["customer service", "customer support", "helpdesk"],
        "terms_in": ["customer support", "customer service executive", "customer care"],
        "skill_presets": ["crm", "zendesk", "communication", "typing", "languages", "office 365"],
        "match_description": False,
    },

    # ---- Engineering ----
    "mechanical": {
        "label": "Mechanical Eng.", "icon": "⚙️", "group": "Engineering",
        "title_keywords": ["mechanical", "koneinsinööri", "konetekniik*", "mechatronics",
                            "mekatroniik*", "production engineer", "tuotantotekniik*",
                            "maintenance engineer", "kunnossap*"],
        "terms_fi": ["konetekniikka", "koneinsinööri", "mekatroniikka", "mechanical engineer"],
        "terms_en": ["mechanical engineer", "mechatronics", "maintenance engineer"],
        "terms_in": ["mechanical engineer", "production engineer", "maintenance engineer"],
        "skill_presets": ["autocad", "solidworks", "catia", "matlab", "plc", "lean"],
        "match_description": False,
    },
    "electrical": {
        "label": "Electrical Eng.", "icon": "🔌", "group": "Engineering",
        "title_keywords": ["electrical", "sähköinsinööri", "sähkötekniik*", "automation engineer",
                            "automaatio*", "electronics", "elektroniik*", "power engineer",
                            "automaatioinsinööri", "sähköasen*"],
        "terms_fi": ["sähkötekniikka", "sähköinsinööri", "automaatioinsinööri", "automaatio"],
        "terms_en": ["electrical engineer", "automation engineer", "electronics engineer"],
        "terms_in": ["electrical engineer", "automation engineer", "electronics engineer"],
        "skill_presets": ["plc", "scada", "autocad electrical", "matlab", "eplan", "instrumentation"],
        "match_description": False,
    },

    # ---- Care & Education ----
    "healthcare": {
        "label": "Healthcare", "icon": "🩺", "group": "Care & Education",
        "title_keywords": ["nurse", "*hoitaja", "nursing", "hoitotyö*",
                            "terveydenhoit*", "midwife", "kätilö", "physiotherapist",
                            "fysioterapeu*", "pharmacist", "apteek*", "caregiver"],
        "terms_fi": ["sairaanhoitaja", "lähihoitaja", "hoitaja"],
        "terms_en": ["nurse", "nursing", "healthcare assistant"],
        "terms_in": ["staff nurse", "nurse", "pharmacist"],
        "skill_presets": ["patient care", "first aid", "medication", "ehr", "hygiene", "empathy"],
        "match_description": False,
    },
    "education": {
        "label": "Education", "icon": "📚", "group": "Care & Education",
        "title_keywords": ["teacher", "*opettaja", "teaching", "lecturer", "*lehtori", "tutor",
                            "educator", "kindergarten", "varhaiskasvat*", "lastentarha*",
                            "*ohjaaja"],
        "terms_fi": ["opettaja", "lehtori", "varhaiskasvatus"],
        "terms_en": ["teacher", "tutor", "lecturer"],
        "terms_in": ["teacher", "teaching", "tutor"],
        "skill_presets": ["curriculum", "classroom management", "lesson planning", "languages",
                           "communication"],
        "match_description": False,
    },

    # ---- Service ----
    "logistics": {
        "label": "Logistics", "icon": "🚚", "group": "Service",
        "title_keywords": ["logistics", "logistiik*", "supply chain", "warehouse", "varasto*",
                            "kuljet*", "transport", "forklift", "trukki", "dispatcher",
                            "freight", "rahti"],
        "terms_fi": ["logistiikka", "varasto", "kuljetus"],
        "terms_en": ["logistics", "warehouse", "supply chain"],
        "terms_in": ["logistics executive", "supply chain", "warehouse executive"],
        "skill_presets": ["sap", "wms", "excel", "forklift license", "inventory", "planning"],
        "match_description": False,
    },
    "hospitality": {
        "label": "Hospitality", "icon": "🍽️", "group": "Service",
        "title_keywords": ["hospitality", "ravintola*", "restaurant", "hotel", "hotelli*", "kokki",
                            "chef", "cook", "waiter", "tarjoil*", "barista", "receptionist",
                            "vastaanot*", "keittiö*"],
        "terms_fi": ["ravintola", "hotelli", "kokki", "tarjoilija"],
        "terms_en": ["chef", "waiter", "hotel receptionist", "barista"],
        "terms_in": ["chef", "hotel staff", "restaurant staff", "barista"],
        "skill_presets": ["cooking", "hygiene passport", "customer service", "pos systems", "languages"],
        "match_description": False,
    },
}

# Legacy alias: scorer and main import ROLE_TRACKS for onboarding/labels.
ROLE_TRACKS = JOB_PROFILES

#: Group display order for onboarding.
PROFILE_GROUPS = ["Tech", "Design", "Business", "Engineering", "Care & Education", "Service"]

_MAX_EN_TERMS = 8  # LinkedIn guest endpoint is rate-limited; keep term count low


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def selected_profiles(profiles: list[str] | None) -> list[str]:
    """Return only valid profile keys, preserving order."""
    if not profiles:
        return []
    return [p for p in profiles if p in JOB_PROFILES]


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s\+#./-]", " ", (text or "").lower())


def keyword_pattern(kw: str) -> str:
    """Regex for one keyword.

    Markers for compound-rich languages (Finnish):
    - trailing ``*`` -> prefix match (``markkinoin*`` hits markkinointipäällikkö)
    - leading ``*``  -> suffix match (``*opettaja`` hits luokanopettaja)
    - otherwise exact word-boundary match (``sales`` never hits salesforce)
    """
    kw = kw.lower()
    if kw.startswith("*"):
        return re.escape(kw[1:]) + r"\b"
    if kw.endswith("*"):
        return r"\b" + re.escape(kw[:-1])
    return r"\b" + re.escape(kw) + r"\b"


def _hits(text_norm: str, keywords: list[str]) -> bool:
    for kw in keywords:
        if re.search(keyword_pattern(kw), text_norm):
            return True
    return False


def keep_job(title: str, description: str, profiles: list[str] | None) -> bool:
    """True if the job matches at least one selected profile.

    Title matches always count; description matches only for profiles with
    match_description=True (IT-style profiles where stack keywords appear in
    body text). Business/service profiles are title-only to avoid false
    positives (e.g. every second job description mentions "sales").
    """
    chosen = selected_profiles(profiles)
    if not chosen:
        return True  # no profiles selected -> caller keeps legacy behavior
    title_norm = _normalize(title)
    desc_norm = _normalize(description)
    for key in chosen:
        info = JOB_PROFILES[key]
        if _hits(title_norm, info["title_keywords"]):
            return True
        if info.get("match_description") and _hits(desc_norm, info["title_keywords"]):
            return True
    return False


def _union_terms(profiles: list[str] | None, field: str, cap: int | None = None) -> list[str]:
    seen: dict[str, None] = {}
    for key in selected_profiles(profiles):
        for term in JOB_PROFILES[key][field]:
            seen.setdefault(term, None)
    terms = list(seen)
    return terms[:cap] if cap else terms


def fi_search_terms(profiles: list[str] | None) -> list[str]:
    """Finnish query terms (duunitori). Empty selection -> legacy config terms."""
    terms = _union_terms(profiles, "terms_fi")
    return terms or list(settings.search_terms)


def en_search_terms(profiles: list[str] | None, cap: int | None = None) -> list[str]:
    """English query terms (englishjobs, jobly, linkedin)."""
    return _union_terms(profiles, "terms_en", cap=cap)


def in_search_terms(profiles: list[str] | None) -> list[str]:
    """India query terms (shine, internshala). Empty -> legacy config terms."""
    terms = _union_terms(profiles, "terms_in")
    return terms or list(settings.indian_search_terms)


def linkedin_terms(profiles: list[str] | None) -> list[str]:
    """English terms capped for LinkedIn's rate-limited guest endpoint."""
    return en_search_terms(profiles, cap=_MAX_EN_TERMS)


def skill_presets_for(profiles: list[str] | None) -> list[str]:
    """Skill chips for the onboarding skills step (dedup'd union)."""
    return _union_terms(profiles, "skill_presets")


def bonus_keywords_for(profiles: list[str] | None) -> dict[str, list[str]]:
    """profile key -> bonus keywords (used by the scorer's track bonus)."""
    return {
        key: JOB_PROFILES[key]["title_keywords"]
        for key in selected_profiles(profiles)
    }


def has_non_tech(profiles: list[str] | None) -> bool:
    """True if any selected profile is outside the Tech group."""
    return any(
        JOB_PROFILES[key]["group"] not in ("Tech", "Design")
        for key in selected_profiles(profiles)
    )

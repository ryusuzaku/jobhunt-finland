from pathlib import Path
from pydantic_settings import BaseSettings

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    app_name: str = "JobHunt Finland"
    debug: bool = False

    # Optional "Support this project" link (Ko-fi / Sponsors / ...).
    # Shown in the footer and empty states when set; hidden otherwise.
    support_url: str = ""

    # Dashboard pagination
    dashboard_page_size: int = 50

    # Database
    database_url: str = f"sqlite:///{DATA_DIR / 'jobs.db'}"

    # Request settings
    user_agent: str = "JobHunt-FI/1.0 (personal job search aggregator)"
    request_timeout: int = 30
    cache_ttl_seconds: int = 1800  # 30 minutes

    # Duunitori API
    duunitori_base_url: str = "https://duunitori.fi/api/v1/jobentries"
    duunitori_max_age_days: int = 45
    duunitori_max_pages_per_term: int = 10

    # The Hub API
    thehub_base_url: str = "https://thehub.io/api/jobs"

    # EnglishJobs.fi
    englishjobs_base_url: str = "https://englishjobs.fi/jobs"

    # Search terms to cover junior tech roles in Finland
    search_terms: list[str] = [
        "junior developer",
        "junior ohjelmistokehittäjä",
        "trainee developer",
        "software developer",
        "web developer",
        "frontend developer",
        "backend developer",
        "full stack developer",
        "data engineer",
        "data analyst",
        "machine learning engineer",
        "AI developer",
        "devops engineer",
        "test automation engineer",
    ]

    # Indian job-board search terms (Bengaluru)
    indian_search_terms: list[str] = [
        "python developer",
        "software developer",
        "frontend developer",
        "backend developer",
        "full stack developer",
        "data analyst",
        "data engineer",
        "machine learning engineer",
        "devops engineer",
    ]

    # Finnish IT company career-page list (JSON: name, career_url, ats, slug)
    company_careers_file: str = str(DATA_DIR / "finnish_companies.json")

    # Default preferences (can be overridden via dashboard)
    default_preferred_tech: list[str] = [
        "python", "javascript", "typescript", "react", "node.js",
        "sql", "docker", "aws", "azure", "git", "c#", "java",
    ]
    default_preferred_locations: list[str] = [
        "helsinki", "espoo", "vantaa", "tampere", "turku", "oulu",
        "bengaluru", "bangalore",
    ]

    # Locations that are allowed to appear in the dashboard and API.
    # Jobs whose location does not contain one of these tokens are hidden.
    allowed_dashboard_locations: list[str] = [
        "helsinki", "espoo", "vantaa", "tampere", "turku", "lahti",
        "bengaluru", "bangalore",
    ]
    default_remote_ok: bool = True
    default_hybrid_ok: bool = True

    # Scoring weights
    weight_learning: float = 0.35
    weight_worklife: float = 0.25
    weight_tech: float = 0.25
    weight_company: float = 0.15

    # Alerts
    alert_threshold: float = 60.0
    alert_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    # Webhook alerts
    discord_webhook_url: str | None = None
    slack_webhook_url: str | None = None

    class Config:
        env_file = ROOT_DIR / ".env"
        env_file_encoding = "utf-8"


settings = Settings()

from pathlib import Path
import json
from typing import Annotated
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    app_name: str = "JobHunt Finland"
    debug: bool = False
    app_log_file: str = str(ROOT_DIR / "logs" / "application.log")

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
    source_timeout_seconds: int = Field(default=120, ge=1, le=600)
    source_concurrency: int = Field(default=3, ge=1, le=5)
    enable_linkedin: bool = False  # Restricted source: requires an explicit local opt-in.

    # Duunitori API
    duunitori_base_url: str = "https://duunitori.fi/api/v1/jobentries"
    duunitori_max_age_days: int = 45
    duunitori_max_pages_per_term: int = 10

    # The Hub API
    thehub_base_url: str = "https://thehub.io/jobs/location/finland"

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
    default_preferred_tech: Annotated[list[str], NoDecode] = [
        "python", "javascript", "typescript", "react", "node.js",
        "sql", "docker", "aws", "azure", "git", "c#", "java",
    ]
    default_preferred_locations: Annotated[list[str], NoDecode] = [
        "helsinki", "espoo", "vantaa", "tampere", "turku", "oulu",
        "bengaluru", "bangalore",
    ]

    # Locations that are allowed to appear in the dashboard and API.
    # Jobs whose location does not contain one of these tokens are hidden.
    allowed_dashboard_locations: Annotated[list[str], NoDecode] = [
        "helsinki", "espoo", "vantaa", "tampere", "turku", "lahti",
        "bengaluru", "bangalore",
        # Some sources (e.g. Jobly) only say "Finland" for country-wide
        # listings; without this token those jobs never reach the feed.
        "finland",
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

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("default_preferred_tech", "default_preferred_locations", "allowed_dashboard_locations", mode="before")
    @classmethod
    def parse_csv_or_json_list(cls, value):
        if isinstance(value, str):
            value = json.loads(value) if value.lstrip().startswith("[") else value.split(",")
        return list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))


settings = Settings()

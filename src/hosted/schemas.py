"""Pydantic request schemas and hosted profile compatibility helpers."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from src.config import settings
from src.profile_schema import ProfileUpdate

PROFILE_KEYS = (
    "job_profiles",
    "role_tracks",
    "experience_level",
    "preferred_tech",
    "preferred_locations",
    "remote_ok",
    "hybrid_ok",
    "alert_threshold",
    "onboarding_completed",
)
APPLICATION_STATUSES = ("saved", "applied", "interview", "offer", "rejected", "withdrawn", "ghosted")


def default_profile_values() -> dict[str, Any]:
    """Return independent defaults in the legacy scorer preference shape."""
    return {
        "job_profiles": [],
        "role_tracks": [],
        "experience_level": "junior",
        "preferred_tech": list(settings.default_preferred_tech),
        "preferred_locations": list(settings.default_preferred_locations),
        "remote_ok": bool(settings.default_remote_ok),
        "hybrid_ok": bool(settings.default_hybrid_ok),
        "alert_threshold": float(settings.alert_threshold),
        "onboarding_completed": False,
    }


class ProfilePayload(ProfileUpdate):
    """A partial profile patch with optional optimistic-lock revision."""

    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int | None = Field(default=None, ge=0)


class DraftPayload(ProfileUpdate):
    """Validated partial wizard state; saving it never completes onboarding."""

    model_config = ConfigDict(extra="forbid", strict=True)
    step: int = Field(ge=1, le=6)
    revision: int | None = Field(default=None, ge=0)


class SaveJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    saved: StrictBool


class ApplicationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["saved", "applied", "interview", "offer", "rejected", "withdrawn", "ghosted"]
    applied_at: datetime | date | None = None
    closing_date: datetime | date | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    outcome: str | None = Field(default=None, max_length=10_000)

    @field_validator("applied_at", "closing_date", mode="before")
    @classmethod
    def browser_dates(cls, value):
        if value == "" or value is None:
            return None
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Use a valid ISO calendar date") from exc
        return value

    @field_validator("notes", "outcome")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


def as_utc_datetime(value: datetime | date | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def profile_values(profile: Any) -> dict[str, Any]:
    """Serialize the stable preference keys without exposing ORM internals."""
    result = {key: getattr(profile, key) for key in PROFILE_KEYS}
    result.update(
        revision=profile.revision,
        draft=dict(profile.draft or {}),
        draft_step=profile.draft_step,
        profile_updated_at=(profile.updated_at.isoformat() if profile.updated_at else None),
    )
    return result


def profile_updates(payload: ProfilePayload | DraftPayload) -> dict[str, Any]:
    """Return only supplied, scorer-compatible preference keys."""
    raw = payload.model_dump(exclude_unset=True)
    return {key: raw[key] for key in PROFILE_KEYS if key in raw}


def merged_profile_values(profile: Any, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge a patch into persisted values and normalize compatibility aliases."""
    merged = default_profile_values()
    if profile is not None:
        merged.update({key: getattr(profile, key) for key in PROFILE_KEYS})
    merged.update(updates)
    # Legacy callers may still send role_tracks. Keep both representations
    # synchronized unless a canonical job_profiles value was supplied too.
    if "role_tracks" in updates and "job_profiles" not in updates:
        merged["job_profiles"] = list(merged["role_tracks"])
    if "job_profiles" in updates and "role_tracks" not in updates:
        merged["role_tracks"] = list(merged["job_profiles"])
    return merged


def validate_completed_profile(values: dict[str, Any]) -> None:
    """Raise ValueError when a reviewed onboarding profile lacks essential choices."""
    if not values.get("job_profiles"):
        raise ValueError("Choose at least one job field before completing onboarding")
    if not values.get("experience_level"):
        raise ValueError("Choose an experience level before completing onboarding")
    if not values.get("preferred_locations"):
        raise ValueError("Choose at least one preferred location before completing onboarding")

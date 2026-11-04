"""Validation shared by the JSON profile API and HTML preferences form."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from src.job_profiles import JOB_PROFILES


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    job_profiles: list[str] | None = Field(default=None, max_length=25)
    role_tracks: list[str] | None = Field(default=None, max_length=25)
    experience_level: Literal["student", "graduate", "junior", "mid"] | None = None
    preferred_tech: list[str] | None = Field(default=None, max_length=100)
    preferred_locations: list[str] | None = Field(default=None, max_length=100)
    remote_ok: StrictBool | None = None
    hybrid_ok: StrictBool | None = None
    alert_threshold: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    onboarding_completed: StrictBool | None = None
    profile_updated_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Profile must be a JSON object")
        for key in cls.model_fields:
            if key in values and values[key] is None:
                raise ValueError(f"{key} cannot be null")
        return values

    @field_validator("job_profiles", "role_tracks", "preferred_tech", "preferred_locations")
    @classmethod
    def normalize_lists(cls, values):
        if values is None:
            return values
        cleaned = []
        for value in values:
            value = value.strip().lower()
            if not value or len(value) > 100:
                raise ValueError("Selections must be non-empty strings of at most 100 characters")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    @field_validator("job_profiles", "role_tracks")
    @classmethod
    def known_profiles(cls, values):
        if values is not None and any(value not in JOB_PROFILES for value in values):
            raise ValueError("Unknown job profile")
        return values

    @field_validator("profile_updated_at")
    @classmethod
    def valid_sync_timestamp(cls, value):
        if value is not None:
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid profile timestamp") from exc
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp.astimezone(timezone.utc).isoformat()
        return value

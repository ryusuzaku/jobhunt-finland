import json
from sqlalchemy.orm import Session

from src.config import settings
from src.models import Preference


DEFAULT_PREFERENCES = {
    "preferred_tech": settings.default_preferred_tech,
    "preferred_locations": settings.default_preferred_locations,
    "remote_ok": settings.default_remote_ok,
    "hybrid_ok": settings.default_hybrid_ok,
    "alert_threshold": settings.alert_threshold,
    # Onboarding profile (empty/absent = current behaviour, no personalization)
    "role_tracks": [],                # e.g. ["software", "data"]
    "experience_level": "junior",     # student | graduate | junior | mid
    "onboarding_completed": False,
    "profile_updated_at": "",         # ISO timestamp, used for local-first sync
}


def _encode(value) -> str:
    return json.dumps(value)


def _decode(raw: str | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def get_preferences(db: Session) -> dict:
    prefs = DEFAULT_PREFERENCES.copy()
    rows = db.query(Preference).all()
    for row in rows:
        val = _decode(row.value)
        prefs[row.key] = val
    return prefs


def set_preference(db: Session, key: str, value) -> None:
    raw = _encode(value)
    row = db.query(Preference).filter(Preference.key == key).first()
    if row:
        row.value = raw
    else:
        row = Preference(key=key, value=raw)
        db.add(row)
    db.commit()


def set_preferences(db: Session, updates: dict) -> dict:
    for key, value in updates.items():
        if key in DEFAULT_PREFERENCES:
            set_preference(db, key, value)
    return get_preferences(db)

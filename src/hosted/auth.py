"""Manus OAuth and JWT authentication for the hosted entry point.

There is deliberately no guest, preview-only, or development authentication path.
Preview auto-login works because it uses the documented ``webdev_app_session``
cookie and is subjected to the same HS256/project/expiry verification as OAuth.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from fastapi import HTTPException, Request

try:  # Parent owns the PyJWT dependency declaration/installation.
    import jwt
except ImportError:  # pragma: no cover - exercised only before dependency installation
    jwt = None  # type: ignore[assignment]

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import HostedProfile, HostedUser
from .schemas import default_profile_values

SESSION_COOKIE = "webdev_app_session"
OAUTH_NONCE_COOKIE = "jh_oauth_nonce"
CRON_COOKIE = "app_session_id"


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AuthSettings:
    project_id: str | None
    jwt_secret: str | None
    oauth_portal_url: str | None
    oauth_api_url: str | None
    # A deployment may set one canonical public origin. It is an allow-list,
    # never a client-provided redirect destination.
    public_origin: str | None = None
    cookie_secure: bool = True

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        origin = os.getenv("MANUS_APP_ORIGIN") or os.getenv("PUBLIC_APP_URL")
        return cls(
            project_id=os.getenv("MANUS_PROJECT_ID"),
            jwt_secret=os.getenv("MANUS_JWT_SECRET"),
            oauth_portal_url=os.getenv("MANUS_OAUTH_PORTAL_URL"),
            oauth_api_url=os.getenv("MANUS_OAUTH_API_URL"),
            public_origin=origin.rstrip("/") if origin else None,
            # Hosted/Preview cookies need Secure and SameSite=None because the
            # Preview frame is cross-site. Tests pass an explicit false setting.
            cookie_secure=os.getenv("MANUS_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"},
        )


def _require_jwt(settings: AuthSettings) -> None:
    if jwt is None:
        raise AuthError("Authentication dependency is unavailable", 503)
    if not settings.project_id or not settings.jwt_secret:
        raise AuthError("Hosted authentication is not configured", 503)


def _decode_project_jwt(token: str, settings: AuthSettings) -> dict[str, Any]:
    _require_jwt(settings)
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
    except Exception as exc:
        invalid = getattr(jwt, "InvalidTokenError", Exception)
        if isinstance(exc, invalid):
            raise AuthError("Invalid or expired session", 401) from exc
        raise AuthError("Session validation failed", 401) from exc
    if claims.get("appId") != settings.project_id:
        raise AuthError("Session is for a different project", 401)
    return claims


def session_claims_from_request(request: Request, settings: AuthSettings) -> dict[str, Any]:
    """Read only the documented application cookie or a valid Bearer JWT."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
    if not token:
        raise AuthError("Authentication required", 401)
    claims = _decode_project_jwt(token, settings)
    if not isinstance(claims.get("openId"), str) or not claims["openId"]:
        raise AuthError("Session has no Manus identity", 401)
    if claims["openId"].startswith("cron_") or len(claims["openId"]) > 255:
        raise AuthError("Session is not an application user", 403)
    return claims


def get_or_create_user(db: Session, claims: dict[str, Any]) -> tuple[HostedUser, HostedProfile]:
    """Resolve a verified Manus identity to the hosted ownership rows."""
    open_id = claims["openId"]
    user = db.scalar(select(HostedUser).where(HostedUser.open_id == open_id))
    name = str(claims.get("name") or "")[:255]
    email = str(claims.get("email") or "")[:320]
    if user is None:
        user = HostedUser(open_id=open_id, name=name, email=email, csrf_token=secrets.token_urlsafe(32))
        db.add(user)
        db.flush()
    else:
        # OAuth/preview identity updates should be reflected, but absent claims
        # must never erase a value learned from a prior OAuth lookup.
        if name:
            user.name = name
        if email:
            user.email = email
        if not user.csrf_token:
            user.csrf_token = secrets.token_urlsafe(32)
    profile = db.scalar(select(HostedProfile).where(HostedProfile.user_id == user.id))
    if profile is None:
        profile = HostedProfile(user_id=user.id, **default_profile_values())
        db.add(profile)
        db.flush()
    db.commit()
    return user, profile


def require_csrf(request: Request, user: HostedUser) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not user.csrf_token or not hmac.compare_digest(supplied, user.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


def _validated_origin(value: str, status: int = 400) -> str:
    parsed = urlparse(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or "\\" in value):
        raise AuthError("Frontend origin is invalid", status)
    return value.rstrip("/")


def public_origin_for_request(request: Request, settings: AuthSettings, frontend_origin: str | None = None) -> str:
    """Use an explicit browser origin, never the internal proxy request Host."""
    configured = _validated_origin(settings.public_origin, 503) if settings.public_origin else None
    if frontend_origin is None:
        if configured:
            return configured
        raise AuthError("Open the app and use its sign-in button to start securely", 400)
    origin = _validated_origin(frontend_origin)
    supplied = request.headers.get("origin")
    if not supplied or _validated_origin(supplied) != origin:
        raise AuthError("Sign-in origin did not match this browser request", 400)
    if configured and configured != origin:
        raise AuthError("Sign-in origin is not allowed by this deployment", 400)
    parsed = urlparse(origin)
    if parsed.scheme == "http" and (settings.cookie_secure or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}):
        raise AuthError("Hosted sign-in requires HTTPS", 400)
    return origin


def callback_url(request: Request, settings: AuthSettings, frontend_origin: str | None = None) -> str:
    return f"{public_origin_for_request(request, settings, frontend_origin)}/auth/callback"


def _b64json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_oauth_state(value: str) -> dict[str, Any]:
    try:
        padded = value + "=" * (-len(value) % 4)
        parsed = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthError("OAuth state is invalid", 400) from exc
    if not isinstance(parsed, dict):
        raise AuthError("OAuth state is invalid", 400)
    redirect_uri = parsed.get("redirectUri")
    nonce = parsed.get("nonce")
    parsed_uri = urlparse(redirect_uri) if isinstance(redirect_uri, str) else None
    if not isinstance(nonce, str) or not nonce or not parsed_uri or parsed_uri.scheme not in {"http", "https"}:
        raise AuthError("OAuth state is invalid", 400)
    return parsed


def begin_oauth(request: Request, settings: AuthSettings, frontend_origin: str | None = None) -> tuple[str, str]:
    """Bind the actual frontend callback to this browser in a short-lived signed cookie."""
    _require_jwt(settings)
    if not settings.oauth_portal_url:
        raise AuthError("Manus OAuth is not configured", 503)
    redirect_uri = callback_url(request, settings, frontend_origin)
    nonce = secrets.token_urlsafe(32)
    state = _b64json({"redirectUri": redirect_uri, "nonce": nonce})
    binding = jwt.encode({
        "appId": settings.project_id, "purpose": "oauth-state", "nonce": nonce,
        "redirectUri": redirect_uri, "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }, settings.jwt_secret, algorithm="HS256")
    endpoint = urljoin(settings.oauth_portal_url.rstrip("/") + "/", "app-auth")
    query = urlencode({"appId": settings.project_id, "redirectUri": redirect_uri, "state": state, "responseType": "code"})
    return f"{endpoint}?{query}", binding


def verify_oauth_nonce(state: str, browser_binding: str | None, settings: AuthSettings) -> dict[str, Any]:
    parsed = parse_oauth_state(state)
    if not browser_binding:
        raise AuthError("Sign-in expired. Return to the app and start again", 400)
    try:
        binding = _decode_project_jwt(browser_binding, settings)
    except AuthError as exc:
        raise AuthError("Sign-in expired or its browser binding is invalid", 400) from exc
    if (binding.get("purpose") != "oauth-state"
            or not isinstance(binding.get("nonce"), str)
            or not hmac.compare_digest(parsed["nonce"], binding["nonce"])
            or parsed["redirectUri"] != binding.get("redirectUri")):
        raise AuthError("OAuth state did not match this browser", 400)
    return parsed


async def exchange_code_for_identity(code: str, redirect_uri: str, settings: AuthSettings) -> dict[str, Any]:
    """Exchange an OAuth authorization code and retrieve the authoritative user identity."""
    _require_jwt(settings)
    if not settings.oauth_api_url:
        raise AuthError("Manus OAuth is not configured", 503)
    base = settings.oauth_api_url.rstrip("/") + "/"
    exchange_url = urljoin(base, "webdev.v1.WebDevAuthPublicService/ExchangeToken")
    info_url = urljoin(base, "webdev.v1.WebDevAuthPublicService/GetUserInfo")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            exchange = await client.post(
                exchange_url,
                json={
                    "clientId": settings.project_id,
                    "grantType": "authorization_code",
                    "code": code,
                    "redirectUri": redirect_uri,
                },
            )
            exchange.raise_for_status()
            token = exchange.json().get("accessToken")
            if not isinstance(token, str) or not token:
                raise AuthError("OAuth token exchange returned no access token", 502)
            info = await client.post(info_url, json={"accessToken": token})
            info.raise_for_status()
            identity = info.json()
    except AuthError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthError("Manus OAuth identity lookup failed", 502) from exc
    if not isinstance(identity, dict) or not isinstance(identity.get("openId"), str) or not identity["openId"]:
        raise AuthError("Manus OAuth identity lookup returned no user", 502)
    return identity


def issue_session(identity: dict[str, Any], settings: AuthSettings) -> str:
    """Issue a short-lived app session signed with the project JWT secret."""
    _require_jwt(settings)
    now = datetime.now(timezone.utc)
    claims = {
        "appId": settings.project_id,
        "openId": identity["openId"],
        "name": str(identity.get("name") or "")[:255],
        "email": str(identity.get("email") or "")[:320],
        "iat": now,
        "exp": now + timedelta(hours=8),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def cookie_options(settings: AuthSettings) -> dict[str, Any]:
    return {"httponly": True, "secure": settings.cookie_secure, "samesite": "none" if settings.cookie_secure else "lax", "path": "/"}


async def resolve_scheduled_identity(request: Request, settings: AuthSettings) -> dict[str, Any]:
    """Verify a scheduler ticket then resolve its task UID at Manus.

    The callback body is intentionally not inspected for identity. A caller must
    have an HS256 project JWT whose cron openId is subsequently verified by the
    documented GetUserInfoWithJwt endpoint.
    """
    token = request.cookies.get(CRON_COOKIE)
    if not token:
        raise AuthError("Scheduled callback authentication required", 401)
    claims = _decode_project_jwt(token, settings)
    open_id = claims.get("openId")
    if not isinstance(open_id, str) or not open_id.startswith("cron_"):
        raise AuthError("Session is not a scheduler identity", 403)
    if not settings.oauth_api_url:
        raise AuthError("Manus OAuth API is not configured", 503)
    resolver = getattr(request.app.state, "scheduled_identity_resolver", None)
    if resolver is not None:
        # This hook exists solely for isolated unit tests; production creation
        # never sets it and always performs the platform identity lookup.
        resolved = await resolver(token, settings.project_id)
    else:
        endpoint = urljoin(
            settings.oauth_api_url.rstrip("/") + "/",
            "webdev.v1.WebDevAuthPublicService/GetUserInfoWithJwt",
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    endpoint,
                    json={"jwt_token": token, "project_id": settings.project_id},
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                resolved = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthError("Scheduled identity lookup failed", 502) from exc
    if not isinstance(resolved, dict) or resolved.get("openId") != open_id:
        raise AuthError("Scheduled identity verification failed", 401)
    task_uid = resolved.get("taskUid")
    if not isinstance(task_uid, str) or not task_uid:
        raise AuthError("Scheduled identity has no task UID", 401)
    return resolved

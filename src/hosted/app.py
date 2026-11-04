"""Hosted, multi-user FastAPI entry point for JobHunt.

Run this application as ``src.hosted.app:app`` in the managed environment. It is
kept separate from ``src.main`` so the existing local SQLite fallback remains
untouched.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from src.job_profiles import JOB_PROFILES, PROFILE_GROUPS

from .auth import (
    AuthError,
    AuthSettings,
    OAUTH_NONCE_COOKIE,
    SESSION_COOKIE,
    begin_oauth,
    callback_url,
    cookie_options,
    exchange_code_for_identity,
    get_or_create_user,
    issue_session,
    require_csrf,
    resolve_scheduled_identity,
    session_claims_from_request,
    verify_oauth_nonce,
)
from .models import (
    HostedApplication,
    HostedFetchRun,
    HostedJob,
    HostedProfile,
    HostedSavedJob,
    HostedSchedule,
    HostedUser,
    create_hosted_engine,
    make_session_factory,
)
from .queries import (
    acquire_refresh,
    execute_refresh,
    fetch_run_to_dict,
    get_presented_job,
    list_applications,
    list_jobs,
    source_health,
)
from .schemas import (
    ApplicationPayload,
    DraftPayload,
    ProfilePayload,
    SaveJobPayload,
    as_utc_datetime,
    merged_profile_values,
    profile_updates,
    profile_values,
    validate_completed_profile,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT_DIR / "src" / "templates"
STATIC_DIR = ROOT_DIR / "src" / "static" / "hosted"


def _user_context(user: HostedUser) -> dict[str, Any]:
    return {"id": user.id, "open_id": user.open_id, "name": user.name, "email": user.email}


def _skill_map() -> dict[str, list[str]]:
    return {key: list(value.get("skill_presets", [])) for key, value in JOB_PROFILES.items()}


def _default_filters() -> dict[str, Any]:
    return {
        "q": "",
        "location": "",
        "work": "",
        "source": "",
        "min_score": 0.0,
        "sort": "match",
        "show_applied": False,
    }


def _template_context(
    request: Request,
    *,
    user: HostedUser | None = None,
    profile: HostedProfile | None = None,
    page: str,
    **values: Any,
) -> dict[str, Any]:
    """Supply every field in the shared hosted Jinja contract, even when empty."""
    context: dict[str, Any] = {
        "request": request,
        "user": _user_context(user) if user else None,
        "profile": profile_values(profile) if profile else {},
        "page": page,
        "csrf_token": user.csrf_token if user else "",
        "jobs": [],
        "total": 0,
        "page_number": 1,
        "page_count": 1,
        "filters": _default_filters(),
        "applications": [],
        "job": None,
        "source_status": {},
        "profile_catalog": JOB_PROFILES,
        "profile_groups": PROFILE_GROUPS,
        "skill_map": _skill_map(),
    }
    context.update(values)
    return context


def _html_auth_error(error: AuthError) -> RedirectResponse:
    # Page routes should return the useful public landing rather than an API JSON
    # blob. API dependencies below preserve the precise authentication failure.
    response = RedirectResponse(url="/", status_code=303)
    if error.status_code == 401:
        response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def create_app(
    *,
    database_url: str | None = None,
    auth_settings: AuthSettings | None = None,
    scheduled_identity_resolver: Callable[..., Any] | None = None,
) -> FastAPI:
    """Build the hosted application without creating schemas or starting services.

    ``database_url`` and the identity resolver are dependency-injection seams for
    isolated tests only. Deployment uses the environment-provided managed URL and
    direct Manus identity endpoint.
    """
    app = FastAPI(title="JobHunt Hosted", version="1.0")
    app.state.auth_settings = auth_settings or AuthSettings.from_environment()
    app.state.scheduled_identity_resolver = scheduled_identity_resolver
    app.state.refresh_tasks: set[asyncio.Task] = set()

    @app.exception_handler(StaleDataError)
    async def profile_conflict(_request: Request, _error: StaleDataError):
        return JSONResponse({"detail": "Profile changed on another device; reload before saving"}, status_code=409)

    resolved_database_url = database_url or os.getenv("DATABASE_URL")
    if resolved_database_url:
        app.state.engine = create_hosted_engine(resolved_database_url)
        app.state.session_factory = make_session_factory(app.state.engine)
    else:
        # The service can still render its public landing and truthful health
        # response while deployment configuration has not supplied DATABASE_URL.
        app.state.engine = None
        app.state.session_factory = None

    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static/hosted", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="hosted-static")
    app.mount("/static/fonts", StaticFiles(directory=str(ROOT_DIR / "src" / "static" / "fonts")), name="hosted-fonts")

    def get_db(request: Request):
        factory: sessionmaker[Session] | None = request.app.state.session_factory
        if factory is None:
            raise HTTPException(status_code=503, detail="Hosted database is not configured")
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def current_context(request: Request, db: Session = Depends(get_db)) -> tuple[HostedUser, HostedProfile]:
        try:
            claims = session_claims_from_request(request, request.app.state.auth_settings)
            return get_or_create_user(db, claims)
        except AuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    def render(template: str, request: Request, *, user: HostedUser | None = None, profile: HostedProfile | None = None, page: str, **context: Any):
        return templates.TemplateResponse(
            request=request,
            name=f"hosted/{template}",
            context=_template_context(request, user=user, profile=profile, page=page, **context),
        )

    @app.middleware("http")
    async def hosted_cache_policy(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/api/", "/auth/", "/jobs/")) or request.url.path in {"/", "/discover", "/saved", "/tracker", "/profile", "/onboarding"}:
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie"
        elif request.url.path == "/service-worker.js":
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Service-Worker-Allowed"] = "/"
        return response

    @app.get("/", response_class=HTMLResponse)
    def root(request: Request):
        factory: sessionmaker[Session] | None = request.app.state.session_factory
        if factory is None:
            return render("landing.html", request, page="landing")
        db = factory()
        try:
            user, profile = current_context(request, db)
        except HTTPException:
            return render("landing.html", request, page="landing")
        finally:
            db.close()
        if not profile.onboarding_completed:
            return RedirectResponse(url="/onboarding", status_code=303)
        return RedirectResponse(url="/discover", status_code=303)

    @app.get("/discover", response_class=HTMLResponse)
    def discover(
        request: Request,
        page: int = Query(1, ge=1),
        q: str = "",
        location: str = "",
        work: str = "",
        source: str = "",
        min_score: float = Query(0.0, ge=0, le=100),
        sort: str = "match",
        show_applied: bool = False,
        db: Session = Depends(get_db),
    ):
        try:
            user, profile = current_context(request, db)
        except HTTPException as exc:
            return _html_auth_error(AuthError(str(exc.detail), exc.status_code))
        if not profile.onboarding_completed:
            return RedirectResponse(url="/onboarding", status_code=303)
        work = ",".join(request.query_params.getlist("work"))
        listing = list_jobs(
            db,
            user_id=user.id,
            prefs=profile_values(profile),
            page=page,
            q=q,
            location=location,
            work=work,
            source=source,
            min_score=min_score,
            sort=sort,
            show_applied=show_applied,
        )
        return render(
            "discover.html",
            request,
            user=user,
            profile=profile,
            page="discover",
            jobs=listing["jobs"],
            total=listing["total"],
            page_number=listing["page"],
            page_count=listing["page_count"],
            filters=listing["filters"],
            source_status=source_health(db),
            pagination_query=urlencode([(key, value) for key, value in request.query_params.multi_items() if key != "page"]),
        )

    @app.get("/saved", response_class=HTMLResponse)
    def saved(request: Request, page: int = Query(1, ge=1), db: Session = Depends(get_db)):
        try:
            user, profile = current_context(request, db)
        except HTTPException as exc:
            return _html_auth_error(AuthError(str(exc.detail), exc.status_code))
        listing = list_jobs(
            db,
            user_id=user.id,
            prefs=profile_values(profile),
            page=page,
            saved_only=True,
            show_applied=True,
        )
        return render(
            "saved.html",
            request,
            user=user,
            profile=profile,
            page="saved",
            jobs=listing["jobs"],
            total=listing["total"],
            page_number=listing["page"],
            page_count=listing["page_count"],
            filters=listing["filters"],
            source_status=source_health(db),
            pagination_query="",
        )

    @app.get("/tracker", response_class=HTMLResponse)
    def tracker(request: Request, db: Session = Depends(get_db)):
        try:
            user, profile = current_context(request, db)
        except HTTPException as exc:
            return _html_auth_error(AuthError(str(exc.detail), exc.status_code))
        applications = list_applications(db, user.id, profile_values(profile))
        return render(
            "tracker.html",
            request,
            user=user,
            profile=profile,
            page="tracker",
            applications=applications,
            source_status=source_health(db),
        )

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, db: Session = Depends(get_db)):
        try:
            user, profile = current_context(request, db)
        except HTTPException as exc:
            return _html_auth_error(AuthError(str(exc.detail), exc.status_code))
        return render("profile.html", request, user=user, profile=profile, page="profile", source_status=source_health(db))

    @app.get("/onboarding", response_class=HTMLResponse)
    def onboarding_page(request: Request, db: Session = Depends(get_db)):
        try:
            user, profile = current_context(request, db)
        except HTTPException as exc:
            return _html_auth_error(AuthError(str(exc.detail), exc.status_code))
        return render("onboarding.html", request, user=user, profile=profile, page="onboarding")

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(job_id: int, request: Request, db: Session = Depends(get_db)):
        try:
            user, profile = current_context(request, db)
        except HTTPException as exc:
            return _html_auth_error(AuthError(str(exc.detail), exc.status_code))
        job = get_presented_job(db, user.id, profile_values(profile), job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return render("job.html", request, user=user, profile=profile, page="job", job=job, source_status=source_health(db))

    @app.get("/offline", response_class=HTMLResponse)
    def offline(request: Request):
        return render("offline.html", request, page="offline")

    @app.get("/manifest.webmanifest")
    def manifest():
        path = STATIC_DIR / "manifest.webmanifest"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Hosted manifest is not available")
        return FileResponse(path, media_type="application/manifest+json")

    @app.get("/service-worker.js")
    def service_worker():
        path = STATIC_DIR / "service-worker.js"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Hosted service worker is not available")
        return FileResponse(path, media_type="application/javascript")

    @app.get("/health")
    def health(request: Request):
        factory: sessionmaker[Session] | None = request.app.state.session_factory
        if factory is None:
            return JSONResponse({"ok": False, "error": "Hosted database is not configured"}, status_code=503)
        try:
            with factory() as db:
                db.execute(text("SELECT 1"))
                db.execute(select(HostedUser.id).limit(1))
                db.execute(select(HostedProfile.id).limit(1))
                db.execute(select(HostedJob.id).limit(1))
        except Exception:
            return JSONResponse({"ok": False, "error": "Hosted database unavailable"}, status_code=503)
        return {"ok": True, "service": "jobhunt-hosted"}

    @app.get("/manus-routes.json")
    def manus_routes():
        return {
            "routes": [
                {"path": "/", "title": "JobHunt"},
                {"path": "/discover", "title": "Discover"},
                {"path": "/saved", "title": "Saved"},
                {"path": "/tracker", "title": "Application tracker"},
                {"path": "/profile", "title": "Profile"},
                {"path": "/onboarding", "title": "Your direction"},
                {"path": "/jobs/:job_id", "title": "Job details"},
                {"path": "/offline", "title": "Offline"},
            ]
        }

    @app.post("/auth/start")
    async def auth_start_browser(request: Request):
        settings: AuthSettings = request.app.state.auth_settings
        try:
            payload = await request.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("origin"), str):
                raise AuthError("Frontend origin is required", 400)
            authorize_url, binding = begin_oauth(request, settings, payload["origin"])
        except (ValueError, AuthError) as exc:
            return JSONResponse({"ok": False, "error": getattr(exc, "message", "Sign-in input is invalid")}, status_code=getattr(exc, "status_code", 400))
        response = JSONResponse({"ok": True, "authorize_url": authorize_url})
        response.set_cookie(OAUTH_NONCE_COOKIE, binding, max_age=600, httponly=True,
                            secure=settings.cookie_secure, samesite="lax", path="/auth/callback")
        return response

    @app.get("/auth/start")
    def auth_start(request: Request):
        settings: AuthSettings = request.app.state.auth_settings
        try:
            authorize_url, nonce = begin_oauth(request, settings)
        except AuthError as exc:
            return JSONResponse({"ok": False, "error": exc.message}, status_code=exc.status_code)
        response = RedirectResponse(authorize_url, status_code=303)
        # OAuth's top-level redirect needs Lax so the nonce returns on callback.
        response.set_cookie(
            OAUTH_NONCE_COOKIE,
            nonce,
            max_age=600,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/auth/callback",
        )
        return response

    @app.get("/auth/callback")
    async def auth_callback(request: Request, code: str = "", state: str = ""):
        settings: AuthSettings = request.app.state.auth_settings
        try:
            parsed = verify_oauth_nonce(state, request.cookies.get(OAUTH_NONCE_COOKIE), settings)
            if not code:
                raise AuthError("OAuth callback did not include an authorization code", 400)
            identity = await exchange_code_for_identity(code, parsed["redirectUri"], settings)
            token = issue_session(identity, settings)
        except AuthError as exc:
            response = JSONResponse({"ok": False, "error": exc.message}, status_code=exc.status_code)
            response.delete_cookie(OAUTH_NONCE_COOKIE, path="/auth/callback")
            return response
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(OAUTH_NONCE_COOKIE, path="/auth/callback")
        response.set_cookie(SESSION_COOKIE, token, max_age=8 * 60 * 60, **cookie_options(settings))
        return response

    @app.post("/auth/logout")
    def logout(request: Request, context: tuple[HostedUser, HostedProfile] = Depends(current_context)):
        user, _profile = context
        require_csrf(request, user)
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/profile")
    def api_profile(context: tuple[HostedUser, HostedProfile] = Depends(current_context)):
        user, profile = context
        return {**profile_values(profile), "csrf_token": user.csrf_token}

    def _save_profile(
        request: Request,
        payload: ProfilePayload,
        context: tuple[HostedUser, HostedProfile],
        *,
        complete: bool = False,
    ) -> dict[str, Any]:
        user, profile = context
        require_csrf(request, user)
        if payload.revision is not None and payload.revision != profile.revision:
            raise HTTPException(status_code=409, detail="Profile changed elsewhere; reload before saving")
        updates = profile_updates(payload)
        if not updates and not (complete and profile.draft):
            raise HTTPException(status_code=400, detail="No profile values were supplied")
        if updates.get("onboarding_completed") is True and not complete:
            raise HTTPException(status_code=400, detail="Use profile completion to finish onboarding")
        # A six-step wizard may submit its reviewed draft with only a revision
        # on the final request. Explicit final-request values win over draft
        # values, and both have already passed the same profile validation.
        reviewed_updates = {**(profile.draft or {}), **updates} if complete else updates
        merged = merged_profile_values(profile, reviewed_updates)
        if complete:
            try:
                validate_completed_profile(merged)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            merged["onboarding_completed"] = True
        for key, value in merged.items():
            setattr(profile, key, value)
        profile.revision += 1
        # A real profile save supersedes the matching draft but keeps its step
        # only for a completed user who intentionally revisits onboarding.
        profile.draft = {} if complete else dict(profile.draft or {})
        return {"ok": True, "profile": profile_values(profile)}

    @app.post("/api/profile")
    def api_profile_save(
        request: Request,
        payload: ProfilePayload,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        # current_context and db are the same request-scoped session dependency.
        result = _save_profile(request, payload, context, complete=False)
        db.commit()
        return result

    @app.post("/api/profile/complete")
    def api_profile_complete(
        request: Request,
        payload: ProfilePayload,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        result = _save_profile(request, payload, context, complete=True)
        db.commit()
        return result

    @app.post("/api/profile/draft")
    def api_profile_draft(
        request: Request,
        payload: DraftPayload,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        user, profile = context
        require_csrf(request, user)
        if payload.revision is not None and payload.revision != profile.revision:
            raise HTTPException(status_code=409, detail="Profile changed elsewhere; reload before saving this draft")
        updates = profile_updates(payload)
        draft = dict(profile.draft or {})
        draft.update(updates)
        draft["onboarding_completed"] = False
        profile.draft = draft
        profile.draft_step = payload.step
        profile.revision += 1
        db.commit()
        return {"ok": True, "profile": profile_values(profile)}

    @app.get("/api/jobs")
    def api_jobs(
        page: int = Query(1, ge=1),
        q: str = "",
        location: str = "",
        work: str = "",
        source: str = "",
        min_score: float = Query(0.0, ge=0, le=100),
        sort: str = "match",
        show_applied: bool = False,
        request: Request = None,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        user, profile = context
        if request is not None:
            work = ",".join(request.query_params.getlist("work"))
        listing = list_jobs(
            db,
            user_id=user.id,
            prefs=profile_values(profile),
            page=page,
            q=q,
            location=location,
            work=work,
            source=source,
            min_score=min_score,
            sort=sort,
            show_applied=show_applied,
        )
        return {"jobs": listing["jobs"], "total": listing["total"], "page": listing["page"], "page_count": listing["page_count"]}

    @app.post("/api/jobs/{job_id}/save")
    def save_job(
        job_id: int,
        request: Request,
        payload: SaveJobPayload,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        user, _profile = context
        require_csrf(request, user)
        job = db.get(HostedJob, job_id)
        if job is None or job.hidden:
            raise HTTPException(status_code=404, detail="Job not found")
        saved = db.scalar(
            select(HostedSavedJob).where(HostedSavedJob.user_id == user.id, HostedSavedJob.job_id == job_id)
        )
        if payload.saved and saved is None:
            db.add(HostedSavedJob(user_id=user.id, job_id=job_id))
        elif not payload.saved and saved is not None:
            db.delete(saved)
        db.commit()
        return {"ok": True, "saved": payload.saved}

    @app.post("/api/jobs/{job_id}/application")
    def upsert_application(
        job_id: int,
        request: Request,
        payload: ApplicationPayload,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        user, _profile = context
        require_csrf(request, user)
        job = db.get(HostedJob, job_id)
        if job is None or job.hidden:
            raise HTTPException(status_code=404, detail="Job not found")
        application = db.scalar(
            select(HostedApplication).where(HostedApplication.user_id == user.id, HostedApplication.job_id == job_id)
        )
        if application is None:
            application = HostedApplication(user_id=user.id, job_id=job_id, status=payload.status)
            db.add(application)
        application.status = payload.status
        application.applied_at = as_utc_datetime(payload.applied_at)
        application.closing_date = as_utc_datetime(payload.closing_date)
        application.notes = payload.notes
        application.outcome = payload.outcome
        db.commit()
        db.refresh(application)
        return {"ok": True, "application": {"id": application.id, "status": application.status, "applied_at": application.applied_at.isoformat() if application.applied_at else None, "closing_date": application.closing_date.isoformat() if application.closing_date else None, "notes": application.notes or "", "outcome": application.outcome or ""}}

    @app.delete("/api/applications/{application_id}")
    def delete_application(
        application_id: int,
        request: Request,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        user, _profile = context
        require_csrf(request, user)
        application = db.scalar(
            select(HostedApplication).where(HostedApplication.id == application_id, HostedApplication.user_id == user.id)
        )
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        db.delete(application)
        db.commit()
        return {"ok": True}

    @app.post("/api/fetch")
    async def fetch(
        request: Request,
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        user, _profile = context
        require_csrf(request, user)
        run, started = acquire_refresh(db, triggered_by_user_id=user.id)
        db.commit()
        if started:
            result = await execute_refresh(run.id, request.app.state.session_factory)
        else:
            result = await _wait_for_refresh(run.id, request.app.state.session_factory)
        return JSONResponse({**result, "started": started}, status_code=200 if result.get("ok") else 502)

    @app.get("/api/fetch/status")
    def fetch_status(
        context: tuple[HostedUser, HostedProfile] = Depends(current_context),
        db: Session = Depends(get_db),
    ):
        _user, _profile = context
        latest = db.scalar(select(HostedFetchRun).order_by(HostedFetchRun.id.desc()))
        state = fetch_run_to_dict(latest)
        if state.get("status") not in {"queued", "running"}:
            state["sources"] = source_health(db) or state.get("sources", {})
        return state

    async def _wait_for_refresh(run_id: int, factory: sessionmaker[Session], timeout_seconds: float = 780.0) -> dict[str, Any]:
        """Poll durable state when another worker already owns a bounded run."""
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            with factory() as polling_db:
                run = polling_db.get(HostedFetchRun, run_id)
                if run is None:
                    raise HTTPException(status_code=500, detail="Scheduled refresh state disappeared")
                if run.status in {"success", "error"}:
                    return fetch_run_to_dict(run)
            await asyncio.sleep(0.5)
        raise HTTPException(status_code=503, detail="Scheduled refresh exceeded its bounded wait")

    @app.post("/api/scheduled/refresh")
    async def scheduled_refresh(request: Request, db: Session = Depends(get_db)):
        settings: AuthSettings = request.app.state.auth_settings
        try:
            identity = await resolve_scheduled_identity(request, settings)
        except AuthError as exc:
            return JSONResponse({"ok": False, "error": exc.message}, status_code=exc.status_code)
        schedule = db.scalar(
            select(HostedSchedule).where(HostedSchedule.task_uid == identity["taskUid"], HostedSchedule.enabled.is_(True))
        )
        if schedule is None:
            # Truthful: the route is present in published code but no schedule
            # was registered/bound by this backend.
            return JSONResponse({"ok": False, "error": "No enabled refresh schedule is bound to this task"}, status_code=404)
        run, started = acquire_refresh(db, triggered_by_user_id=None)
        if started:
            result = await execute_refresh(run.id, request.app.state.session_factory)
        else:
            result = await _wait_for_refresh(run.id, request.app.state.session_factory)
        if result.get("status") != "success":
            return JSONResponse({"ok": False, "refresh": result}, status_code=502)
        schedule.last_run_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "refresh": result}

    return app


# Importing this module is side-effect free with respect to managed schema/data.
app = create_app()

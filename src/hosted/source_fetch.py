"""Hosted source fetching without importing the legacy scraper or SQLite models.

The small in-memory HTTP cache is performance-only. Durable fallback listings live
in jh_jobs, so a new container does not lose the last successful source result.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextvars import ContextVar
from datetime import timedelta
import time
from typing import Any

import httpx
from sqlalchemy import select

from src.config import settings
from src.job_profiles import keep_job, selected_profiles
from src.sources import (
    DuunitoriSource, TheHubSource, EnglishJobsSource, JoblySource,
    AcademicWorkSource, LinkedInSource, RemoteOKSource, RemotiveSource,
    WorkingNomadsSource, WeWorkRemotelySource, HasjobSource, ShineSource,
    InternshalaSource, CompanyCareersSource,
)
from .models import HostedFetchRun, HostedJob, HostedProfile, utcnow

SOURCE_TYPES = (
    DuunitoriSource, TheHubSource, EnglishJobsSource, JoblySource,
    AcademicWorkSource, LinkedInSource, RemoteOKSource, RemotiveSource,
    WorkingNomadsSource, WeWorkRemotelySource, HasjobSource, ShineSource,
    InternshalaSource, CompanyCareersSource,
)
_HTTP_CACHE: OrderedDict[str, tuple[float, bytes, int, dict, str]] = OrderedDict()
_CACHE_BYTES = 0
_SOURCE = ContextVar("hosted_source", default="unknown")


class HostedHttpClient(httpx.AsyncClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache_hits: dict[str, int] = {}
        self.network_calls: dict[str, int] = {}

    async def get(self, url, *, cache_ttl=None, **kwargs):
        global _CACHE_BYTES
        ttl = getattr(settings, "cache_ttl_seconds", 1800) if cache_ttl is None else cache_ttl
        target = httpx.URL(url)
        if kwargs.get("params"):
            target = target.copy_merge_params(kwargs["params"])
        key = str(target)
        cached = _HTTP_CACHE.get(key)
        name = _SOURCE.get()
        if cached and ttl > 0 and time.monotonic() - cached[0] < ttl:
            self.cache_hits[name] = self.cache_hits.get(name, 0) + 1
            _HTTP_CACHE.move_to_end(key)
            headers = {key: value for key, value in cached[3].items() if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}}
            return httpx.Response(cached[2], content=cached[1], headers=headers, request=httpx.Request("GET", cached[4]))
        self.network_calls[name] = self.network_calls.get(name, 0) + 1
        response = await super().get(url, **kwargs)
        if response.is_success and ttl > 0 and len(response.content) <= 1024 * 1024:
            if key in _HTTP_CACHE:
                _CACHE_BYTES -= len(_HTTP_CACHE.pop(key)[1])
            _HTTP_CACHE[key] = (time.monotonic(), response.content, response.status_code, dict(response.headers), str(response.url))
            _CACHE_BYTES += len(response.content)
            while _CACHE_BYTES > 8 * 1024 * 1024 and _HTTP_CACHE:
                _CACHE_BYTES -= len(_HTTP_CACHE.popitem(last=False)[1][1])
        return response


def _active_profiles(factory) -> list[str]:
    with factory() as db:
        rows = db.scalars(select(HostedProfile).where(HostedProfile.onboarding_completed.is_(True))).all()
        union = list(dict.fromkeys(key for row in rows for key in (row.job_profiles or row.role_tracks or [])))
    return selected_profiles(union) or ["software", "frontend", "data", "devops", "mobile", "qa", "security"]


def _cached_jobs(factory, source: str) -> list[dict[str, Any]]:
    with factory() as db:
        rows = db.scalars(select(HostedJob).where(HostedJob.source == source, HostedJob.hidden.is_(False), HostedJob.updated_at >= utcnow() - timedelta(days=7))).all()
        fields = [column.name for column in HostedJob.__table__.columns if column.name not in {"id", "created_at", "updated_at", "hidden"}]
        return [{key: getattr(row, key) for key in fields} for row in rows]


def _progress(factory, run_id: int, states: dict) -> None:
    with factory() as db:
        run = db.get(HostedFetchRun, run_id)
        if run:
            run.source_status = {name: dict(value) for name, value in states.items()}
            db.commit()


async def fetch_hosted_sources(factory, run_id: int):
    profiles = await asyncio.to_thread(_active_profiles, factory)
    sources = [kind() for kind in SOURCE_TYPES]
    states = {source.name: {"status": "queued", "count": 0} for source in sources}
    semaphore = asyncio.Semaphore(settings.source_concurrency)
    progress_lock = asyncio.Lock()

    async def update(name, value):
        async with progress_lock:
            states[name] = value
            await asyncio.to_thread(_progress, factory, run_id, states)

    async def fetch_source(source, client):
        name = source.name
        if name == "linkedin" and not settings.enable_linkedin:
            await update(name, {"status": "disabled", "count": 0})
            return []
        async with semaphore:
            token = _SOURCE.set(name)
            try:
                await update(name, {"status": "running", "count": 0})
                source.active_profiles = profiles
                previous = await asyncio.to_thread(_cached_jobs, factory, name)
                try:
                    raw = await asyncio.wait_for(source.fetch(client), settings.source_timeout_seconds)
                    normalized = []
                    rejected = 0
                    for item in raw:
                        try:
                            job = source.normalize(item)
                            if job and keep_job(job.get("title"), job.get("description"), profiles):
                                normalized.append(job)
                        except Exception:
                            rejected += 1
                    if normalized:
                        state = "cached" if client.cache_hits.get(name) and not client.network_calls.get(name) else "fresh"
                        jobs = normalized
                    else:
                        jobs = [job for job in previous if keep_job(job.get("title"), job.get("description"), profiles)]
                        state = "cached" if jobs else "empty"
                    details = {"status": state, "count": len(jobs)}
                    if rejected:
                        details["normalization_errors"] = rejected
                    await update(name, details)
                    return jobs
                except Exception as exc:
                    jobs = [job for job in previous if keep_job(job.get("title"), job.get("description"), profiles)]
                    await update(name, {"status": "cached" if jobs else "error", "count": len(jobs), "error": type(exc).__name__})
                    return jobs
            finally:
                _SOURCE.reset(token)

    await asyncio.to_thread(_progress, factory, run_id, states)
    async with HostedHttpClient(timeout=settings.request_timeout, follow_redirects=True, limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)) as client:
        results = await asyncio.gather(*(fetch_source(source, client) for source in sources))
    return [job for batch in results for job in batch], states

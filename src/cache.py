"""HTTP response cache + fetched-job snapshot cache.

The ResponseCache sits on top of httpx and caches GET responses in a small
SQLite database so we don't hammer sources on every refresh.  The snapshot
cache keeps a JSON mirror of the last normalized result set per source so a
source that fails or returns empty can fall back to its previous jobs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx

from src.config import settings, DATA_DIR

logger = logging.getLogger(__name__)

CACHE_DIR = DATA_DIR
CACHE_DIR.mkdir(exist_ok=True)
RESPONSE_CACHE_DB = CACHE_DIR / "response_cache.db"
SNAPSHOT_CACHE_FILE = CACHE_DIR / "fetch_snapshot.json"

DEFAULT_TTL_SECONDS = int(getattr(settings, "cache_ttl_seconds", 1800))  # 30 min


class _CachedResponse:
    """Minimal httpx.Response stand-in for cached data."""

    def __init__(
        self,
        *,
        status_code: int,
        text: str,
        headers: dict,
        url: str,
        request: httpx.Request,
    ):
        self.status_code = status_code
        self.text = text
        self.headers = httpx.Headers(headers)
        self.url = httpx.URL(url)
        self._request = request
        self._content = text.encode("utf-8")

    @property
    def content(self) -> bytes:
        return self._content

    def json(self, **kwargs):
        return json.loads(self.text, **kwargs)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Cached {self.status_code} error for url: {self.url}",
                request=self._request,
                response=self,
            )


class ResponseCache:
    """SQLite-backed cache for HTTP GET responses."""

    def __init__(self, db_path: Path = RESPONSE_CACHE_DB):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    key TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    headers TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_responses_ts ON responses(timestamp)"
            )
            conn.commit()

    @staticmethod
    def _make_key(url: str | httpx.URL, params: dict | None = None) -> str:
        full_url = httpx.URL(url)
        if params:
            full_url = full_url.copy_merge_params(params)
        # Normalize the query string so key is stable regardless of kwarg order.
        query = urlencode(sorted(full_url.params.multi_items()))
        return f"GET {full_url.scheme}://{full_url.host}{full_url.path}?{query}"

    async def get(
        self,
        url: str | httpx.URL,
        params: dict | None = None,
        ttl: int | None = None,
    ) -> _CachedResponse | None:
        ttl = ttl if ttl is not None else DEFAULT_TTL_SECONDS
        if ttl <= 0:
            return None

        key = self._make_key(url, params)

        def _fetch():
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT url, status_code, text, headers, timestamp FROM responses WHERE key = ?",
                    (key,),
                ).fetchone()
                return row

        async with self._lock:
            row = await asyncio.to_thread(_fetch)
        if not row:
            return None

        url_str, status_code, text, headers_json, timestamp = row
        age = time.time() - timestamp
        if age > ttl:
            return None

        headers = json.loads(headers_json)
        request = httpx.Request("GET", url_str)
        return _CachedResponse(
            status_code=status_code,
            text=text,
            headers=headers,
            url=url_str,
            request=request,
        )

    async def set(self, url: str | httpx.URL, response: httpx.Response, params: dict | None = None):
        key = self._make_key(url, params)
        text = response.text
        headers = dict(response.headers)
        timestamp = time.time()

        def _store():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO responses (key, url, status_code, text, headers, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        url=excluded.url,
                        status_code=excluded.status_code,
                        text=excluded.text,
                        headers=excluded.headers,
                        timestamp=excluded.timestamp
                    """,
                    (
                        key,
                        str(response.url),
                        response.status_code,
                        text,
                        json.dumps(headers),
                        timestamp,
                    ),
                )
                conn.commit()

        async with self._lock:
            await asyncio.to_thread(_store)

    async def clear(self):
        def _clear():
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("DELETE FROM responses")
                conn.commit()

        async with self._lock:
            await asyncio.to_thread(_clear)


class CachedAsyncClient:
    """httpx.AsyncClient-compatible client that caches GET responses."""

    def __init__(
        self,
        *,
        timeout: float | httpx.Timeout = 30.0,
        limits: httpx.Limits | None = None,
        ttl: int | None = None,
        follow_redirects: bool = True,
    ):
        if limits is None:
            limits = httpx.Limits()
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=follow_redirects,
        )
        self._cache = ResponseCache()
        self.ttl = ttl if ttl is not None else DEFAULT_TTL_SECONDS

    async def get(
        self,
        url: str | httpx.URL,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        cache_ttl: int | None = None,
        **kwargs,
    ) -> httpx.Response:
        ttl = cache_ttl if cache_ttl is not None else self.ttl
        cached = await self._cache.get(url, params=params, ttl=ttl)
        if cached is not None:
            logger.debug("Cache hit: %s", self._cache._make_key(url, params))
            return cached

        response = await self._client.get(url, params=params, headers=headers, **kwargs)
        # Only cache successful or server-error-ish responses; skip redirects explicitly.
        try:
            await self._cache.set(url, response, params=params)
        except Exception as exc:
            logger.warning("Failed to cache response for %s: %s", url, exc)
        return response

    async def post(self, *args, **kwargs):
        return await self._client.post(*args, **kwargs)

    async def aclose(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()


def _json_default(obj):
    """JSON serializer fallback for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _deserialize(obj):
    """Best-effort deserialize ISO date strings back into datetime objects."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = _deserialize(v)
            if k == "date_posted" and isinstance(out[k], str):
                try:
                    out[k] = datetime.fromisoformat(out[k])
                except ValueError:
                    pass
        return out
    if isinstance(obj, list):
        return [_deserialize(v) for v in obj]
    return obj


class JobSnapshotCache:
    """JSON mirror of the last fetched result set per source.

    This lets the scraper fall back to previous jobs when a source is down
    or rate-limited, and gives us a quick way to diff "what changed".
    """

    def __init__(self, path: Path = SNAPSHOT_CACHE_FILE, max_age_days: int = 7):
        self.path = path
        self.max_age_days = max_age_days
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")

    def get(self, source: str) -> list[dict]:
        entries = self._data.get(source, {})
        cutoff = time.time() - (self.max_age_days * 86400)
        return [
            _deserialize(item["job"])
            for item in entries.values()
            if item.get("last_seen", 0) > cutoff
        ]

    def update(self, source: str, jobs: list[dict]):
        now = time.time()
        entries = self._data.setdefault(source, {})
        for job in jobs:
            key = f"{job.get('source')}:{job.get('source_id')}"
            entries[key] = {"job": job, "last_seen": now}
        self._prune(source)
        self._save()

    def _prune(self, source: str):
        cutoff = time.time() - (self.max_age_days * 86400)
        entries = self._data.get(source, {})
        stale = [k for k, v in entries.items() if v.get("last_seen", 0) < cutoff]
        for k in stale:
            del entries[k]

    def diff(self, source: str, jobs: list[dict]) -> tuple[list[dict], list[dict]]:
        """Return (new_jobs, removed_jobs) compared to the previous snapshot."""
        old_keys = set(self._data.get(source, {}).keys())
        new_keys = {f"{j.get('source')}:{j.get('source_id')}" for j in jobs}
        new = [j for j in jobs if f"{j.get('source')}:{j.get('source_id')}" not in old_keys]
        removed = [self._data[source][k]["job"] for k in old_keys - new_keys]
        return new, removed

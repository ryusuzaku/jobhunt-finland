# Project Status — JobHunt Finland

Last updated: 2026-07-07

## Current state

The project is a working, self-hosted FastAPI dashboard that aggregates and ranks junior tech jobs for the Finnish market (plus selected global remote roles).

- ✅ Server runs reliably as a detached background process on `http://127.0.0.1:8006/`.
- ✅ 10 active data sources (Duunitori, The Hub, EnglishJobs.fi, Jobly, Academic Work, LinkedIn, RemoteOK, Remotive, Working Nomads, We Work Remotely).
- ✅ ~1,600 visible jobs after de-duplication and filtering.
- ✅ Two-layer caching: HTTP response cache (`data/response_cache.db`) and per-source job snapshot cache (`data/fetch_snapshot.json`).
- ✅ Automatic fallback to snapshots when a source fails or returns empty.
- ✅ Transparent heuristic scoring with user-editable preferences.
- ✅ Dashboard with search, minimum-score filter, source checkboxes, remote/hybrid toggles, and a city filter.
- ✅ Dedicated `/bengaluru` page for Bengaluru/Bangalore jobs only.
- ✅ Server-side pagination on the dashboard and Bengaluru page (no more hard 100-job limit).
- ✅ Application tracker: tag jobs you’re applying for, hide them from the dashboard, and track status / dates / notes / outcomes on a dedicated page.
- ✅ Alerts via console, email, Discord, and Slack.
- ✅ Hide-jobs feature.
- ✅ One-time setup scripts for Windows (`setup.ps1`) and macOS/Linux (`setup.sh`).
- ✅ Start/stop/status helper scripts for Windows and Unix-like systems.

## Recently completed

- Added RemoteOK, Remotive, Working Nomads, and We Work Remotely sources.
- Added HTTP + snapshot caching to avoid hammering sources and to survive transient failures.
- Added a city filter and restricted the dashboard/API to allowed cities.
- Filtered out garbled (mojibake / U+FFFD) titles and locations from remote job boards.
- Fixed a `title` variable bug in `src/sources/remotive.py`.
- Made preferences save return instantly by moving full DB re-scoring to a background task.
- Added server-side dashboard pagination and `skip` support to `/api/jobs`.
- Added an `Application` model and `/applications` tracker page with create/update/delete flows.
- Updated `README.md` and created this `STATUS.md`.

## Known limitations / next steps

- **Oikotie Työpaikat** is not integrated because listings are loaded client-side (requires a headless browser).
- **TE-palvelut / Työmarkkinatori** is not integrated because the API requires authentication.
- **LinkedIn** is scraped conservatively; 429 responses trigger a 2-hour cooldown and fallback to snapshots.
- PowerShell prints occasional non-fatal `cp932` codec warnings when displaying Finnish/Unicode characters; this is a console-encoding issue and does not affect the app.

## How to verify everything is working

1. Run `\.start_server.ps1` (Windows) or `./start_server.sh` (macOS/Linux).
2. Open http://127.0.0.1:8006/ — the dashboard should load with paginated jobs and filters.
3. Click **Track** on a job card, set a status, and save — the job should disappear from the dashboard.
4. Visit http://127.0.0.1:8006/applications — the tracked job should appear with its status and notes.
5. Visit http://127.0.0.1:8006/api/jobs?skip=50&limit=50 — paginated JSON should be returned.
6. Check `logs/uvicorn.err.log` for fetch results and any source errors.

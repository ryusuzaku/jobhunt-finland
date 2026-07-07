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
- ✅ Dashboard with search, minimum-score filter, source checkboxes, remote/hybrid toggles, and a dynamic location filter.
- ✅ Alerts via console, email, Discord, and Slack.
- ✅ Hide-jobs feature.
- ✅ One-time setup scripts for Windows (`setup.ps1`) and macOS/Linux (`setup.sh`).
- ✅ Start/stop/status helper scripts for Windows and Unix-like systems.

## Recently completed

- Added RemoteOK, Remotive, Working Nomads, and We Work Remotely sources.
- Added HTTP + snapshot caching to avoid hammering sources and to survive transient failures.
- Added a dynamic town/location filter populated from the database (`/api/locations`).
- Filtered out garbled (mojibake / U+FFFD) titles and locations from remote job boards.
- Fixed a `title` variable bug in `src/sources/remotive.py`.
- Made preferences save return instantly by moving full DB re-scoring to a background task.
- Updated `README.md` and created this `STATUS.md`.

## Known limitations / next steps

- **Preferences re-scoring** now runs in the background, but very large DBs may still take a while; a progress indicator could be added later.
- **Oikotie Työpaikat** is not integrated because listings are loaded client-side (requires a headless browser).
- **TE-palvelut / Työmarkkinatori** is not integrated because the API requires authentication.
- **LinkedIn** is scraped conservatively; 429 responses trigger a 2-hour cooldown and fallback to snapshots.
- Dashboard currently renders the top 100 jobs server-side; pagination or infinite scroll could improve browsing.
- PowerShell prints occasional non-fatal `cp932` codec warnings when displaying Finnish/Unicode characters; this is a console-encoding issue and does not affect the app.

## How to verify everything is working

1. Run `.\start_server.ps1` (Windows) or `./start_server.sh` (macOS/Linux).
2. Open http://127.0.0.1:8006/ — the dashboard should load with jobs and filters.
3. Visit http://127.0.0.1:8006/api/locations — a JSON list of distinct locations should appear.
4. Visit http://127.0.0.1:8006/preferences — the preferences form should save without hanging.
5. Check `logs/uvicorn.err.log` for fetch results and any source errors.

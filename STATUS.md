# Project Status — JobHunt Finland

Last updated: 2026-07-22 (UI redesign)

## Current state

The project is a working, self-hosted FastAPI dashboard that aggregates and ranks junior tech jobs for the Finnish market (plus selected global remote roles).

- ✅ Server runs reliably as a detached background process on `http://127.0.0.1:8006/`.
- ✅ 14 active data sources (Duunitori, The Hub, EnglishJobs.fi, Jobly, Academic Work, LinkedIn, RemoteOK, Remotive, Working Nomads, We Work Remotely, Hasjob, Shine, Internshala, Finnish company career pages).
- ✅ ~800+ visible jobs after de-duplication, filtering, and stale-job pruning.
- ✅ Indian sources (Bengaluru/Bangalore only): Shine, Internshala, Hasjob — with INR/LPA salary parsing.
- ✅ Finnish IT company career-page scraper: jobs fetched directly from employer ATS endpoints (Greenhouse, Teamtailor, SmartRecruiters) via a curated company list (`data/finnish_companies.json`).
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
- ✅ Cross-source de-duplication: the same role at the same company posted on multiple boards is merged, keeping the best link (career page > board; tracked applications always survive).
- ✅ Indian staffing-agency spam filter: consultancy reposts ("Hiring For ...", "Manpower", "Placements", "Walk-in") are dropped from Shine/Internshala.
- ✅ Auto-restart watchdog: `watchdog.ps1`/`.sh` re-runs the start script when port 8006 is down; installable as a Windows Scheduled Task (`install_watchdog.ps1`) or cron entry (every 5 min + `@reboot`).
- ✅ Product-grade UI redesign: shared base template + Jinja components, compiled Tailwind design system (no Node), mobile bottom tab bar, slide-over filter drawer, dark mode, toasts, skeleton loading.
- ✅ Onboarding questionnaire: 5-step wizard (role tracks, experience level, tech stack, locations, alerts) drives personalized scoring via `/api/profile`.
- ✅ Personalized scoring: role-track bonus (+12 for title matches) and experience-level-scaled seniority penalty; fully backward compatible when unset.
- ✅ PWA: installable on phone/desktop, service worker with app-shell precache + offline fallback, generated brand icons, install prompt.
- ✅ Local-first profile sync: profile mirrored to localStorage, last-write-wins sync with the server (`profile.js`) — the seam for future per-user cloud saves.
- ✅ Server-side filtering: `?q=&min_score=&sources=&locations=&work=` query params; shareable URLs, pagination preserves filters.
- ✅ Non-intrusive support link (`SUPPORT_URL`) in footer/empty states; monetization model documented in `docs/PRODUCT.md`.
- ✅ Job profiles beyond IT: 19 selectable profiles in 6 groups (Tech, Design, Business, Engineering, Care & Education, Service) with curated English + Finnish keyword packs; fetching, filtering, search terms, and scoring all adapt to the selection. Empty selection = legacy tech-only behavior.
- ✅ Sort control: order the feed by match score, date published, or company — preserved across pagination and shareable URLs.
- ✅ Tracking visibility: tracked jobs show a status badge on the dashboard; applied-or-later jobs are filtered out of the feed by default (`?tracked=all` to see them); the old silent track-to-hide behavior is migrated automatically.
- ✅ Within-source dedupe: re-listings of the same opening (same source + title + company + location, order-insensitive) are collapsed; genuine multi-city postings are kept; tracked jobs are never deleted.
- ✅ Country-wide listings (location "Finland", e.g. from Jobly) now reach the dashboard via the `finland` allowed-location token.

## Recently completed

- Rebuilt the entire frontend: base template + component macros (deleted ~700 lines of duplication), compiled Tailwind v3.4 CSS with vendored Inter font and Alpine.js.
- Added the 5-step onboarding wizard, `/api/profile`, and scorer personalization (role tracks + experience levels).
- Generalized to job profiles beyond IT (`src/job_profiles.py`): profile registry with per-profile keyword packs (incl. Finnish compound-aware matching), profile-driven search terms for all query-driven sources, and a central keep-filter in the fetch pipeline.
- Added sort controls (match / newest / company) and proper tracking visibility (badges + tracked filter + startup migration).
- Made the app an installable PWA (manifest, service worker, offline page, icons, local-first profile sync).
- Switched dashboard filtering to server-side query params (fixes the client-filter vs pagination mismatch).
- Added score-explanation popovers, structured salary chips, dark mode, toasts, skeleton loading, and a kanban-style tracker layout.
- Added cross-source job de-duplication (normalized title + company fuzzy match; best-link keeper, tracked applications protected).
- Added an Indian consultancy/staffing-agency spam filter for Shine and Internshala.
- Added an auto-restart watchdog (Windows Scheduled Task / cron) after a machine-sleep incident silently stopped the server.
- Fixed a fetch-loop crash: `datetime.timestamp()` raises `OSError 22` on Windows for pre-1970 dates from broken source data; dedup ranking now uses safe subtraction. Console/stderr streams are also reconfigured to UTF-8 with `errors=replace` so Unicode in scraped titles can never abort a fetch.
- Added Indian job sources for Bengaluru: Shine (HTML), Internshala (HTML), Hasjob (Atom feed).
- Added a Finnish IT company career-page scraper with ATS adapters (Greenhouse, Teamtailor, SmartRecruiters, Lever, Recruitee, Workable, Ashby, BambooHR) and a curated starter list of ~15 companies.
- Extended salary extraction to Indian formats (`4.0 - 8 LPA`, `₹3,00,000 - 5,00,000 /year`, `₹ 15,000 /month`) and added relative-date parsing (`posted 3 days ago`).
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
- **TimesJobs** was attempted but skipped: the search page is now a JS-only Next.js shell with no server-rendered listings.
- **Naukri, Foundit/Monster India, Hirist, CutShort, Indeed India** are not integrated (JS rendering or unofficial/paid APIs only). Can be revisited if Apify/Parse credentials are provided.
- **Hasjob** can legitimately return 0 jobs when its feed has no Bengaluru tech postings; the snapshot fallback covers gaps.
- The company career list is a starter set; add more employers to `data/finnish_companies.json` (see the ATS adapter names in `src/sources/companycareers.py`).
- PowerShell prints occasional non-fatal `cp932` codec warnings when displaying Finnish/Unicode characters; this is a console-encoding issue and does not affect the app.

## How to verify everything is working

1. Run `\.start_server.ps1` (Windows) or `./start_server.sh` (macOS/Linux).
2. Open http://127.0.0.1:8006/ — the dashboard should load with paginated jobs and filters.
3. Click **Track** on a job card, set a status, and save — the job should disappear from the dashboard.
4. Visit http://127.0.0.1:8006/applications — the tracked job should appear with its status and notes.
5. Visit http://127.0.0.1:8006/api/jobs?skip=50&limit=50 — paginated JSON should be returned.
6. Check `logs/uvicorn.err.log` for fetch results and any source errors.

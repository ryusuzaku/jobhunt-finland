# Project status — JobHunt Finland

Updated 2026-10-30 after the broken-onboarding report. The earlier syntax/import-only review was not sufficient to establish that the app worked. This review repaired the UI and exercised database-backed routes, source adapters, background refresh and SQLite concurrency.

## Repaired and verified

The five-step onboarding component now loads from `src/static/js/onboarding.js`, with configuration in an escaped JSON data script. Its JavaScript no longer appears as page text. Page-specific scripts load before Alpine. Profile location JSON is escaped correctly.

Profile updates are validated and saved atomically. Lists are normalized and bounded; malformed arrays, booleans, levels and out-of-range thresholds return errors rather than corrupting saved state. Zero is a valid threshold. Both JSON and form saves stamp the profile, and stale local mirrors cannot overwrite newer server settings. Selected fields and custom preferred cities affect stored-job filtering before pagination.

Repeated checkbox parameters and CSV share links are equivalent. Both remote/hybrid choices and multiple cities work. Sorting and decimal score filters survive pagination. The jobs API follows the feed's field/source/location/work/tracking rules and enforces pagination bounds.

Saved applications stay visible; applied-or-later jobs are hidden from the feed unless `tracked=all`. Existing notes/status/dates are retained in the card form, and dates can be cleared in the tracker. Neither deduplication nor stale pruning deletes tracked applications. Different-city openings are not falsely merged, and duplicate source IDs in one fetch batch do not create duplicate rows.

Startup and manual refresh run in the background through a single-flight controller. `/fetch` returns 202; `/api/fetch/status` exposes real completion/failure and source health. A refresh does not discard an in-progress form. Sources have bounded concurrency and timeouts, and cached fallbacks respect the selected fields without renewing snapshot age.

A live check found SQLite locks after scoring. The database was backed up and its recovery files preserved; SQLite recovered it normally. WAL, busy handling, materialized scoring batches and debounced scheduling now keep independent readers responsive. Scoring does not advance a vacancy's source-freshness timestamp. `/health` reads the database and returns 503 when it is unavailable.

Windows startup uses detached CIM process creation, compatible with PowerShell 5.1/7, and a real health check. Setup aborts on native-command dependency failures. `.env.example` leaves alert channels blank and its CSV defaults load successfully. LinkedIn is disabled by default. Source refresh continues to use the app's native hourly scheduler; no new watchdog or scheduled task was installed.

The PWA worker has root scope, invalidates old caches, bounds cached navigation pages, and never caches live APIs. This establishes code/route correctness, not proof of phone installation or offline behavior on a physical device.

## Validation evidence

- **40 offline regression tests pass** on the project-local Python 3.12 environment, including a file-backed WAL test with multiple scoring batches and concurrent readers.
- Changed Python compiles; JavaScript syntax checks pass; `pip check` reports no broken requirements.
- In the connected browser at 600px width, the full wizard was completed using real controls: two fields, a custom skill, graduate level, remote-off/hybrid-on and threshold zero. The server profile matched those selections; the browser reported no console errors or horizontal overflow.
- On the user's approval, the interrupted browser checks were resumed and completed on the isolated QA app. Two cities, both work modes and two sources returned the expected 37 matches; company sort and search retained the filters. Saved stayed visible, Applied was excluded by default and returned with its badge under Show applied jobs. Notes/applied date were retained, closing date cleared, and an outcome saved. Delete confirmation resolved to removal and restored the job to the feed. Pagination returned 50 then 5 jobs. Refresh retained the draft query and URL. The 600px browser had no console errors or horizontal overflow. Real profile/application fingerprints matched before and after, and the synthetic tracker was cleaned up. The 40-test suite passed again.
- The final tested app is running at `http://127.0.0.1:8006/`. Nine final route checks returned 200: health, jobs API, profile API, locations API, preferences, onboarding, applications, Bengaluru and offline. SQLite `quick_check` returned `ok`, WAL is active, and no QA fixture URLs were present in the real database.
- The final startup refresh completed in about 29 seconds: 25 new, 567 updated and 1,087 non-hidden stored rows. Twelve adapters returned matching results, including The Hub (15 matching entries after field filtering), Jobly and Academic Work. Shine reported a layout error; LinkedIn was disabled. These are run-specific database counts, not guaranteed feed counts or source completeness.
- The Hub's old API returned 404. Its replacement uses the current public Finnish listing route with bounded pagination and returned **180 unique listings** in a source-only check. See https://thehub.io/jobs/location/finland and https://thehub.io/robots.txt. The prohibited widget route is not used.
- No synthetic QA fixture URLs were found in the real jobs database. Test databases/logs are isolated under `.work/qa*`.

## Remaining boundaries

Shine's current HTML lacks readable listing cards. It now reports a layout error rather than claiming an empty working feed. Its integration needs an allowed source/feed or a separate rendering solution. LinkedIn remains disabled unless explicitly permitted. Other upstream sources may fail or return cached/empty results; this is visible under Source health.

This is the self-hosted, single-user app. Hosted multi-user accounts, paid cloud sync, comprehensive company research and additional restricted boards remain future work, not silently included in completion. Email/Discord/Slack delivery was not tested with real credentials, and no applications were submitted to employers.

## Run and verify

On Windows, run `.\start_server.ps1` and open http://127.0.0.1:8006/. If an older worker or script remains cached, use a hard refresh once. Complete onboarding, apply two filter choices, save a job as **Saved**, and then update it to **Applied** in `/applications`. **Saved** stays in the feed; **Applied** requires **Show applied jobs** to appear there.

Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` for the reproducible no-network/no-notification regression suite. Use `/health` and `/api/fetch/status` to distinguish app/database readiness from upstream source health. Recovery backups remain under `.work/backups/`; do not delete SQLite recovery files to resolve a lock.

## Hosted mobile-first redesign — 2026-10-31

The preceding sections describe the 2026-10-30 local-app validation, not the current hosted release. The new hosted entry point is `src.hosted.app:app`; it has a professional phone-first shell, six-step resumable setup, dedicated Saved and Tracker views, real Manus authentication code and per-user managed storage. The original SQLite profile/application data has not been imported or altered. The original local listener was not running when this session resumed; only the separate managed Preview was restored.

Nineteen affected hosted tests now pass, including ownership/CSRF/session checks, draft/profile revisions, simultaneous writer conflicts, preserved filters and pagination, tracker date clearing, duplicate source rows, cached freshness and retained old bookmarks after profile changes. Phone controls use larger text and 16px editable inputs; source progress and visible failure reasons are no longer trapped in a desktop-only sidebar. Public shell assets are versioned v2; private HTML/APIs/notes are not service-worker cache entries.

The 2026-10-31 real hosted refresh completed successfully in about two minutes: 78 new and 802 updated public listings. Twelve adapters returned fresh results; Shine reported `SourceLayoutError` and LinkedIn was disabled. Bounded 50-row MySQL upserts replaced per-listing database lookups. Discovery stops recommending rows not seen by a source for seven days, without deleting saved jobs or application notes; retained older details show a freshness warning.

Deployment is prepared with a pinned dependency lock, a non-root container, `/health`, and uncached server routing. No private local database or backup is an image input. Automatic publishing is disabled. A real browser sign-in and completed onboarding were not yet recorded when the aggregate account check returned zero users/profiles. HTTPS deployment, trusted production OAuth origin, actual phone/cross-device behavior, and production hourly schedule registration remain explicit gates. See `docs/HOSTED.md` and `TODO.md`; do not describe this as already published or fully phone-verified.

## Release continuation — 2026-11-01

The full offline suite now passes 66 tests, including seven proxy-safe OAuth regressions. Browser sign-in passes its actual origin; the server checks the Origin header and signs the nonce/callback URI in a short-lived cookie. Tampering, expiry and callback replay without the consumed cookie fail closed. The internal server Host is no longer used to guess the callback. Public shell assets are v3, and OAuth-sensitive access logging remains disabled.

The restored Preview's health, route manifest and PWA manifest return 200; real authorization initialization returns 200 and anonymous profile access stays 401. Aggregate managed state remains 964 public listings, zero real accounts and zero completed onboarding records. Native LSP registration could not start because the language-server executables are absent; Python compilation, Node syntax checks and the full tests are the completed checks instead.

No deployment exists yet. Move the saved PWA to a stable HTTPS address through the dedicated publication approval rather than repeating expiring local-login handoffs. Real account/phone verification and actual hourly schedule registration remain open; local SQLite data and separate user Git history are preserved.

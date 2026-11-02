# Hosted, mobile-first JobHunt

The hosted version lives alongside the original local app. Its entry point is `src.hosted.app:app`; the SQLite fallback remains `src.main:app` and is not imported by hosted source fetching.

## What is implemented

The warm paper/ink/pine interface uses phone navigation for Discover, Saved, Tracker and Profile, with a deliberate desktop sidebar. Six short setup steps cover fields, experience, skills, places/work preferences, the match guide and an editable review. Drafts are user-scoped locally and saved to the hosted database; profile revisions prevent stale or simultaneous cross-device saves from silently overwriting newer settings.

Saved jobs have their own paginated view. Tracker entries support status, dates, notes and outcomes, with deliberate removal. Applied jobs are excluded by default and can be explicitly included. Job details link to the actual source and explain the match guide. Scores are guidance, not hiring probabilities.

## Storage and authentication

Only additive `jh_` tables are used for hosted users, profiles, public listings, saved jobs, applications, source health, refresh runs and schedule bindings. `scripts/init_hosted.py` prepares them idempotently. Development and deployment share the managed database: tests use separate temporary SQLite databases, not synthetic hosted records.

Manus account authentication validates HS256 project sessions, expiry, project identity and user ownership. Writes require CSRF protection. A real user session is required in Preview too; there is no development login bypass.

The container copies source, its pinned dependency lock and the public company catalog only. It does **not** copy the local jobs database, profile/application data, snapshots, backups, `.env`, or working artifacts. Importing real local data remains a separate decision.

## PWA behavior

The application owns its manifest, icons, offline shell and root-scoped service worker. Phone layouts provide safe-area spacing, large controls and 16px editable inputs to avoid iOS input zoom. Offline mode offers previously viewed public listing details; authenticated HTML, APIs, profile drafts and tracker notes are not service-worker cache entries. Disconnected private changes are not falsely reported as saved.

Actual installation depends on browser support and HTTPS. Physical iOS/Android installation has not been verified.

## Refresh and deployment

The configured container uses `Dockerfile`, honors `PORT` (default 3000), and checks `/health` against the database. Public listings refresh with bounded concurrency/timeouts, one active database lease and 50-row MySQL upsert batches. Cached fallback must not renew an old listing's last-seen timestamp. Source failures remain visible.

The schedule callback authenticates a platform identity and an enabled stored task binding. No in-process hourly timer is assumed to survive autoscaling. A production hourly schedule is **not registered yet**: publication and its exact platform task binding are release work, not completed merely because an endpoint exists.

The browser passes its actual `window.location.origin` to the real OAuth start endpoint; the server requires the matching Origin header and signs the nonce/callback binding in a ten-minute HttpOnly cookie. Callback verification preserves that signed frontend URI even behind a proxy and fails closed on tampering or expiry. It never guesses a callback from the internal request Host. Optional `PUBLIC_APP_URL` / `MANUS_APP_ORIGIN` settings remain a canonical-origin allow-list. The local command's loopback override is process-scoped and must never become a production value. Hosted cookies remain Secure; raw access logging is disabled to avoid exposing OAuth codes.

## Verification and outstanding gates

The complete offline suite passed **66 tests on 2026-11-01**, including seven additional OAuth tests for proxy origins, signed state tampering, expiry, callback consumption and secure cookies. Python compilation and browser JavaScript syntax checks also passed. Native diagnostic launchers respond, but their language-server binaries are absent; do not call LSP checking complete. Real sign-in initialization returned 200 and anonymous profile access remained 401. The initial source run stored 886 listings on 2026-10-30; the 2026-10-31 run added 78 and updated 802, leaving 964 public rows. These are run-specific counts, not availability guarantees. Shine reported a layout error; LinkedIn was disabled. Discovery excludes listings not seen for seven days while retaining bookmarks and tracker notes.

As of the 2026-11-01 aggregate check, there are still no hosted accounts or completed onboarding records. Real sign-in, authenticated browser click-through, actual cross-device/phone behavior, release approval, successful HTTPS deployment and production schedule registration remain explicit gates. Source code and temporary-database tests are not substitutes for those checks. The public app icons are included in source; project-logo CDN metadata is pending an available durable HTTPS address (the documented global upload command is unavailable on this device).

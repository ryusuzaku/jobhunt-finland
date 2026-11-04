# Completion plan — JobHunt Finland

## Goal

Deliver the existing self-hosted job aggregation, ranking, profile and application-tracking app in this workspace. Repair real user flows rather than declaring completion from syntax/import checks. Preserve the user's data and unrelated work.

## Completed in this repair

- [x] Repair raw JavaScript and empty onboarding shown in the user's screenshot.
- [x] Verify all five wizard steps and profile persistence in the connected browser using an isolated QA database.
- [x] Escape Profile JSON and validate all JSON/form preference updates.
- [x] Fix repeated multi-select filters, selected-field coverage, custom cities, sort and score pagination state.
- [x] Cover saved/applied tracking, dates/notes, hide behavior and tracker deletion with isolated database-backed tests.
- [x] Prevent stale pruning and deduplication from deleting tracked jobs; retain genuine separate-city openings.
- [x] Make startup/manual refresh non-blocking, single-flight, bounded and observable.
- [x] Find and repair the live SQLite locking issue; preserve backups and recovery files.
- [x] Add WAL reader/writer concurrency and source-freshness preservation regressions.
- [x] Repair The Hub's removed API using the allowed public Finnish listing pages and verify real returned rows.
- [x] Make Shine's changed layout explicit as an upstream source failure.
- [x] Disable restricted LinkedIn access by default.
- [x] Repair PowerShell 7 startup and safe environment/setup defaults.
- [x] Correct PWA root scope and keep APIs out of offline caches.
- [x] Run 40 offline regression tests, Python/JS syntax checks and dependency consistency checks.
- [x] Restart the real local app and verify real routes, source results and database integrity.
- [x] Update README and STATUS with verified outcomes and limits.
- [x] Complete the authorized filter/tracker browser click-through: multi-select/sort/search, Saved/Applied visibility, notes/dates/outcome, deletion, pagination, refresh draft retention and real-data isolation. Re-run the 40-test suite successfully.

## Not represented as completed

- [ ] Physically test mobile installation/offline reading on a phone.
- [ ] Verify email/Discord/Slack delivery using real authorized credentials.
- [ ] Restore Shine through a permitted readable feed or rendering integration.

These do not imply hosted cloud sync, multi-user accounts, additional authenticated boards, or employer application submissions. Those are outside this local-app repair.

## Key decisions retained

Python/FastAPI, SQLAlchemy/SQLite, server-rendered Jinja/Alpine, heuristic ranking weighted toward learning and work-life fit, local single-user storage, and optional console/email/webhook alerts. Source requests must respect terms, robots policies, cache windows and bounded request limits.

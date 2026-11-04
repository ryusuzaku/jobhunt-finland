# Hosted mobile-first JobHunt — confirmed blueprint

The user confirmed the hosted PWA blueprint on 2026-10-30. Continue in the selected `ninja-code/jobhunt-finland` repository on its approved `master` branch; preserve its dirty worktree and separate user Git. Checkmarks below record implemented and code/data-verified outcomes, not physical-phone or real-login verification. The local SQLite data remains an untouched fallback.

## Professional app shell and daily discovery

- [x] Redesign the existing interface into a cohesive professional UI with clear hierarchy, accessible controls, useful empty/loading/error states, and improved usability across current workflows.
- [x] Deliver genuinely phone-first screens and primary navigation for Discover, Saved, Tracker, and Profile, not a compressed desktop layout. Make controls comfortably tappable, support safe-area insets, and keep desktop layouts deliberate.
- [x] Improve practical filtering, sorting and job-detail presentation, with clear ranking/match context. Retain working aggregation and personalized ranking so recommendations reflect each user's own fields, experience, skills, locations and work preferences. Do not submit applications to employers.

## Guided, resumable onboarding and profile

- [x] Guide fields, experience, skills, preferred locations and work preferences using sensible defaults and validation. Preserve progress across reloads and provide an editable review summary before completion.
- [x] Persist hosted preferences per authenticated user, keep existing preference keys compatible with the scorer, and let the user revisit their setup without losing saved jobs or tracker entries.

## Saved jobs and application tracking

- [x] Let users save and unsave interesting jobs and access a dedicated Saved view across devices.
- [x] Provide a useful tracker for statuses, dates, notes and outcomes, including editable entries and deliberate deletion. Keep Saved and Applied states distinct; saved items remain discoverable, while applied jobs are excluded by default with an explicit way to show them.

## Secure hosted storage and live data

- [ ] Add real Manus account sign-in with validated project sessions and user ownership on every profile, saved-job and tracker operation. No invented Preview user or authentication bypass. **Implementation and isolated security tests are complete; the real browser login/callback is not yet verified.**
- [x] Use the managed durable database for accounts, profiles, preferences, saved jobs and tracker records. Managed development and deployment share that database: no destructive migrations or synthetic production data.
- [ ] Retain source adapters and scoring rules in the existing codebase. Prepare reliable hosted refresh through authenticated, idempotent platform scheduling rather than assuming an in-process hourly timer survives autoscaling. Expose source errors/cached results truthfully. **Worker and authenticated callback are implemented and tested; live MySQL refresh works. Production platform schedule registration remains release work.**

## Installable PWA and connectivity

- [ ] Prepare HTTPS phone access, an application-owned manifest, icons, responsive installation guidance and appropriate offline/connectivity states. Browser installation support varies; do not claim physical-phone validation without evidence. **Manifest, icons, offline shell and installation help are implemented; HTTPS deployment and physical-phone installation are unverified.**
- [x] Keep private responses out of shared service-worker caches. Offline viewing must be clearly labeled and must not pretend a disconnected private write succeeded.

## Preservation and release gates

- [x] Preserve existing source, Git history and the local app. Do not import, overwrite or delete real SQLite profile/application data during development. Any real-data migration requires a separate explicit decision.
- [x] Save a verified managed code version when ready, without public publishing. Initial source checkpoint `5f6379fa49aa9313abce5d20a58971d3a98950a4` was recorded in Manus on 2026-10-31; user Git remains separate.
- [ ] Ask for explicit release approval before publication and deployment-dependent schedule registration.

## Implementation direction

The hosted entry point is alongside the legacy app; source/scoring/profile validation modules are reused. The visual direction is warm paper, ink and restrained pine green, using locally vendored Inter and a compact stylesheet. Cards emphasize title, company, location/work style and one match guide. Safe-area navigation, 16px editable inputs, readable supporting text and a shared phone-visible source status panel replace shrunken desktop controls. Motion honors reduced-motion preferences.

## Verification and remaining release work — 2026-10-31

All 19 affected hosted regression tests pass; the earlier full suite passed 53 tests before the additional checks. Today’s real source run succeeded with 78 new and 802 updated public listings; Shine reported a layout error and LinkedIn was disabled. Cached results do not renew source freshness, and listings not seen for seven days leave discovery without deleting bookmarks or tracker notes.

The managed container declaration and server routing are configured, with automatic publishing disabled. Real sign-in/onboarding is still required: the aggregate account check before browser verification returned zero hosted users and zero completed profiles. Publication approval, the actual trusted HTTPS OAuth origin, successful deployment, the enabled platform task binding and actual phone installation/cross-device verification are not completed by a code checkpoint.

## Release continuation — 2026-11-01

No real account or completed onboarding was saved after the previous handoff; the temporary Preview expired. Continue the real implementation without a simulated user. Correct OAuth to receive the actual browser-visible origin, require its matching Origin header, and sign the nonce/callback binding so reverse-proxy hosts cannot break or redirect the callback. Keep canonical-origin allow-list settings when provided. Stable hosted publication still requires its dedicated approval; account/phone verification and the production hourly binding remain open.

# JobHunt — Product & Monetization Model

This document captures where JobHunt is heading as a product, so today's
architecture decisions don't block tomorrow's business model. Nothing in the
"Future" sections is built yet.

## Principles

- **Never annoying**: no ad networks, no tracking pixels, no paywalled core
  features, no nag banners. Every monetization surface is dismissible or
  invisible unless you go looking for it.
- **Local-first**: the app works fully without an account. Your profile lives
  on your device (localStorage) and syncs to the server you talk to.
- **Honest ranking**: money never changes a job's organic score. Sponsored
  content is always labeled, capped, and relevant.

## Current state (built)

- Self-hosted single-instance app: FastAPI + SQLite, installable PWA.
- Onboarding questionnaire → personal ranking (role tracks, experience
  level, tech stack, locations, work setup, alert threshold).
- Profile sync seam: `GET/POST /api/profile` with `profile_updated_at`
  last-write-wins sync between localStorage and the server
  (`src/static/js/profile.js`). Today there is one profile per instance;
  the same API becomes per-user once auth exists.
- Passive support link: `SUPPORT_URL` in `.env` shows a small
  "☕ Support this project" link in the footer and empty states
  (Ko-fi / Buy Me a Coffee / GitHub Sponsors). Hidden when unset.

## Monetization ladder (for the hosted version)

1. **Donations** — the support link above. Covers small VPS costs at low
   traffic. Zero implementation beyond what exists.
2. **Sponsored pins** (clearly labeled) — at most **one per page**, always
   visually distinct ("Sponsored" tag + different border), always matched to
   the user's chosen role tracks, and **never displacing organic top
   matches**. This is the standard job-board model (LinkedIn/Indeed), made
   acceptable by being honest and capped.
3. **Paid cloud saves** (the sustainable tier) — accounts, per-user profile
   and application-tracker sync across devices, and instant (push/email)
   alerts instead of hourly digests. The free tier remains fully functional
   with local-only storage.

## Future: multi-user architecture (not built)

- **Auth**: magic-link email login (no passwords to store).
- **Per-user data**: add `user_id` to the profile and tracker tables. The
  `/api/profile` endpoint already speaks the right shape; it just gains a
  user scope. Job listings stay shared/global — only preferences, hidden
  jobs, and applications are per-user.
- **Tracker migration**: today's server-side `Application` table becomes the
  paid sync store. The free tier mirrors the tracker into localStorage using
  the exact same pattern as `profile.js` (local-first + last-write-wins).
- **Payments**: Stripe Checkout + webhooks; a single `plan` field on the
  user row (`free` / `supporter` / `pro`) gates cloud sync and instant
  alerts.

## What we will NOT do

- Sell or share user data.
- Let employers pay to influence organic scores.
- Dark patterns: countdown timers, fake scarcity, confirm-shaming.

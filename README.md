# ⚡ JobHunt

A self-hosted, installable (PWA) job-hunting app that aggregates junior-level tech positions in Finland & Bengaluru (plus selected global remote roles) and ranks them by what actually matters for early-career developers.

## What it does

- **Onboards you in 5 questions** — role tracks, experience level, tech stack, locations, and work setup — then ranks every job for *you*. No config files to edit.
- Fetches jobs automatically every hour from 14 sources, including Indian boards (Bengaluru) and Finnish IT companies' own career pages.
- De-duplicates the same role posted on multiple boards, keeping the best link (company career page preferred over aggregators).
- Filters out Indian staffing-agency reposts ("Hiring For ...", "Manpower", "Placements", "Walk-in") so only direct-employer listings remain.
- **Installs on your phone** like a native app (PWA): home-screen icon, offline reading of previously loaded pages, dark mode.
- **Local-first profile**: your answers live on your device and sync to the server — the seam for optional cloud sync later (see `docs/PRODUCT.md`).
- Scores each job on a 0–100 scale using four transparent signals (tap the score ring for the breakdown):
  1. **Learning & growth potential** (junior/trainee/mentor language, career progression)
  2. **Work-life / location fit** (remote/hybrid, flexible hours, preferred cities)
  3. **Tech-stack match** (your preferred technologies)
  4. **Company quality** (startup size, perks, established-but-growing)
- Shows everything in a clean web dashboard with search, score filters, source filters, and a dynamic location filter.
- Sends alerts for new high-scoring jobs via console, email, Discord, or Slack.

## Data sources

| Source | Method | Notes |
|--------|--------|-------|
| **Duunitori** | JSON API | Largest Finnish job board |
| **The Hub** | JSON API | Nordic startup jobs with company metadata, perks, salary ranges |
| **EnglishJobs.fi** | HTML scrape | English-speaking roles in Finland |
| **Jobly** | HTML scrape | Finnish listings (Monster backend) |
| **Academic Work** | HTML scrape | Trainee/junior-focused roles |
| **LinkedIn** | HTML scrape | Public job search cards (respects cooldowns, falls back on failure) |
| **RemoteOK** | JSON API | Global remote tech roles; filtered to Finland/Europe/global |
| **Remotive** | JSON API | Remote software/data/devops roles; location-filtered |
| **Working Nomads** | JSON API | Remote tech jobs; tech-role filter |
| **We Work Remotely** | RSS parse | Remote tech jobs |
| **Shine** | HTML scrape | Indian jobs, Bengaluru/Bangalore only, INR salary parsing |
| **Internshala** | HTML scrape | Indian fresher/intern jobs, Bengaluru only |
| **Hasjob** | Atom feed | Indian tech/startup jobs, Bengaluru only |
| **Company career pages** | ATS JSON APIs | Finnish IT employers via Greenhouse / Teamtailor / SmartRecruiters (see `data/finnish_companies.json`) |

Sources that require JavaScript rendering (Oikotie Työpaikat, TimesJobs, Naukri, Hirist) or authenticated/unofficial APIs (TE-palvelut / Työmarkkinatori, Foundit, CutShort) are intentionally not integrated yet.

### Adding more Finnish companies

Edit `data/finnish_companies.json` and add entries like:

```json
{"name": "Example Corp", "career_url": "https://example.com/careers", "ats": "greenhouse", "slug": "examplecorp"}
```

Supported `ats` values: `greenhouse`, `teamtailor`, `smartrecruiters`, `lever`, `recruitee`, `workable`, `ashby`, `bamboohr`. The `slug` is the company's board identifier (e.g. `boards-api.greenhouse.io/v1/boards/<slug>/jobs` or `<slug>.teamtailor.com/jobs.json`). Only tech roles in the allowed Finnish cities are kept.

## Quick start

**Requirements:** Python 3.11+ on PATH. Everything else (virtualenv, dependencies, `.env`, directories) is handled by the setup script.

### Windows

```powershell
# 1. One-time setup (creates .venv, installs deps, seeds .env)
.\setup.ps1

# 2. Start the server
.\start_server.ps1
```

### macOS / Linux

```bash
# 1. One-time setup
chmod +x setup.sh start_server.sh stop_server.sh server_status.sh
./setup.sh

# 2. Start the server
./start_server.sh
```

Then open http://127.0.0.1:8006/ in your browser — the **onboarding wizard** runs on first visit and personalises the ranking in about a minute.

### Install as an app (PWA)

- **Android/Chrome**: open the dashboard → menu → *Install app* (or tap the install button in the nav when it appears).
- **iOS/Safari**: open the dashboard → Share → *Add to Home Screen*.
- **Desktop Chrome/Edge**: install icon in the address bar.

The installed app works offline for previously loaded pages and syncs your profile when back online.

### Optional: auto-restart watchdog

To keep the server running across crashes and reboots, install the watchdog — it checks every 5 minutes whether port 8006 is listening and restarts the server if not:

```powershell
# Windows (Scheduled Task as the current user)
.\install_watchdog.ps1    # remove later with .\uninstall_watchdog.ps1
```

```bash
# macOS / Linux: add to your crontab (`crontab -e`)
*/5 * * * * /path/to/jobhunt/watchdog.sh
@reboot /path/to/jobhunt/watchdog.sh
```

Watchdog activity is logged to `logs/watchdog.log`.

> The first start takes 1–2 minutes: the app fetches jobs from all sources before it binds the port. Watch progress in `logs/uvicorn.err.log`. Check later runs with `.\server_status.ps1` or `./server_status.sh`.

The default port is `8006`; you can change it in the start scripts if port 8000 is free on your machine.

## Manual setup (if you prefer)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r requirements.txt
# macOS/Linux:
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# edit .env with your email/webhook settings

python -m uvicorn src.main:app --host 127.0.0.1 --port 8006 --reload
```

## How scoring works

Each job gets sub-scores (0–100) for learning, work-life, tech, and company quality. Seniority signals (e.g. *senior, lead, 5+ years*) lower the final score.

Default weights in `src/config.py`:

```python
weight_learning = 0.35
weight_worklife = 0.25
weight_tech   = 0.25
weight_company = 0.15
```

You can edit these weights in the config file and adjust your preferences in the dashboard at `/preferences`.

## Configuration

Copy `.env.example` to `.env` and set any values you want to override:

```bash
# Optional: alert channels
ALERT_EMAIL=you@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=your_app_password

DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Optional: defaults
ALERT_THRESHOLD=60
DEFAULT_PREFERRED_TECH=python,javascript,typescript,react,node.js,sql,docker,aws,azure,git,c#,java
DEFAULT_PREFERRED_LOCATIONS=helsinki,espoo,vantaa,tampere,turku,oulu
```

Only new jobs with a score ≥ `ALERT_THRESHOLD` trigger alerts.

## Frontend architecture

The UI is server-rendered Jinja2 with a compiled Tailwind CSS design system — no Node.js required:

- `src/templates/base.html` — shared shell: responsive nav + mobile bottom tab bar, dark-mode bootstrap, toasts.
- `src/templates/components.html` — Jinja macros: job card, score ring (+ “Why this score” popover), filter drawer, pagination, stat cards, empty states.
- `src/static/app.css` — **compiled** Tailwind output (committed; includes the vendored Inter font and component classes).
- `src/static/vendor/alpine.min.js` — vendored Alpine.js for wizard steps, drawers, and popovers.
- `src/static/sw.js` + `manifest.webmanifest` — PWA service worker (app-shell precache, network-first pages) and install manifest.
- `src/static/js/app.js` / `profile.js` — UI helpers (theme, toasts, refresh, install prompt) and the local-first profile sync layer.

**Rebuilding the CSS** (only needed after editing templates/styles):

```powershell
# one-time: download the Tailwind standalone CLI (v3.4) into tools/
# https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-windows-x64.exe
.\tools\tailwindcss.exe -i src\static\css\input.css -o src\static\app.css --minify
```

Regenerate PWA icons with `python scripts/make_icons.py` (needs Pillow).

## Project structure

```
jobhunt/
├── src/
│   ├── main.py              # FastAPI app, routes, server-side filtering, profile API
│   ├── scraper.py           # Multi-source orchestrator + dedup + DB upsert
│   ├── scorer.py            # Heuristic scoring + role tracks + salary extraction
│   ├── cache.py             # HTTP response cache + per-source job snapshots
│   ├── models.py            # SQLAlchemy models
│   ├── alerts.py            # Console/email/Discord/Slack alerts
│   ├── config.py            # Settings
│   ├── preferences.py       # Profile/preference storage (key-value JSON rows)
│   ├── sources/             # One module per data source
│   ├── static/              # Compiled CSS, vendored JS/fonts, PWA files, icons
│   └── templates/           # base.html + components.html + thin pages
├── data/                    # SQLite DB + response cache (created on first run)
│   └── finnish_companies.json  # Curated Finnish IT employer list for the career-page scraper
├── docs/PRODUCT.md          # Monetization & multi-user model (free local-first, paid cloud saves)
├── scripts/make_icons.py    # Regenerate PWA icons
├── logs/                    # Uvicorn logs (created on first run)
├── requirements.txt
├── setup.ps1 / setup.sh     # One-time install scripts
├── start_server.ps1 / .sh   # Start the background server
├── stop_server.ps1 / .sh    # Stop the background server
├── server_status.ps1 / .sh  # Check if the server is running
├── watchdog.ps1 / .sh       # Restart the server if the port is down
├── install_watchdog.ps1 / uninstall_watchdog.ps1  # Windows Scheduled Task setup
├── README.md
├── STATUS.md                # Current project status
├── .env.example
└── .gitignore
```

## API

A few useful endpoints while the server is running:

- `GET /api/jobs` — ranked JSON list of visible jobs (default top 100)
- `GET /api/locations` — distinct locations used by the dashboard location filter
- `POST /fetch` — trigger an immediate refresh
- `POST /hide/{job_id}` — hide a job from the dashboard

Interactive docs are available at `/docs`.

## Alerts

Supported channels:

- Console (always on)
- Email via SMTP
- Discord webhook
- Slack webhook

Set the relevant environment variables in `.env`; leave channels blank to disable them.

## Roadmap / ideas

- [x] Onboarding questionnaire that personalises ranking
- [x] Installable PWA with offline shell + dark mode
- [x] Server-side, shareable filtering (fixed client-side/pagination mismatch)
- [ ] Hosted multi-user version with optional paid cloud saves (see `docs/PRODUCT.md`)
- [ ] Integrate Oikotie Työpaikat via a headless browser or public feed
- [ ] Integrate TE-palvelut / Työmarkkinatori when API access is available
- [ ] Integrate TimesJobs / Naukri / Hirist / Foundit / CutShort if stable public endpoints or API credentials become available
- [ ] Grow `data/finnish_companies.json` with more Finnish IT employers
- [ ] Company research signals (Glassdoor-like ratings, funding)
- [ ] Machine-learning-based quality scoring
- [ ] RSS / JSON feed output for external dashboards
- [ ] Apply-helper: cover-letter draft, application tracker

## Disclaimer

This project uses public or undocumented APIs and HTML scraping for personal job-search aggregation. Use responsibly and respect each source's terms of service. LinkedIn scraping is done sparingly and is designed to fall back to cached snapshots if blocked.

## License

MIT — feel free to fork and adapt for your own job hunt.

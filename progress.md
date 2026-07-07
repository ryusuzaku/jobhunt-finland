# Progress Log

## Session: 2026-07-04

### Phase 1: Requirements & Discovery
- **Status:** complete
- Actions taken:
  - Initialized planning files.
  - Captured initial user intent.
  - Got user answers on ranking, format, roles, and scope.
  - Researched Finnish junior tech job market and data sources.
- Files created/modified:
  - task_plan.md, findings.md, progress.md

### Phase 2: Planning & Architecture
- **Status:** complete
- Actions taken:
  - Defined MVP scope.
  - Chose Python + FastAPI + SQLite + Jinja2 stack.
- Files created/modified:
  - task_plan.md, findings.md

### Phase 3: MVP Implementation
- **Status:** complete
- Actions taken:
  - Created project structure and dependencies.
  - Implemented Duunitori scraper with pagination and deduplication.
  - Implemented heuristic scoring.
  - Built dashboard and alert bot.
  - Fixed async/event-loop and template issues.
- Files created/modified:
  - src/main.py, src/scraper.py, src/scorer.py, src/models.py, src/alerts.py, src/config.py
  - src/templates/index.html, requirements.txt, README.md, .env.example, .gitignore

### Phase 4: Expanded Features
- **Status:** complete
- Actions taken:
  - Researched and implemented The Hub API source.
  - Implemented EnglishJobs.fi HTML scraper.
  - Documented WorkinFinland (JS-rendered) and LinkedIn (ToS) limitations.
  - Added Preference model and editable preferences page.
  - Added Discord and Slack webhook alerts.
  - Improved salary extraction regex.
  - Added company-level signals (size, founded, perks).
  - Refactored scraper into `src/sources/` package.
  - Updated dashboard to show source badges, remote/hybrid, salary, perks, company score.
  - Updated README and .env.example.
- Files created/modified:
  - src/sources/duunitori.py, thehub.py, englishjobs.py, __init__.py
  - src/preferences.py
  - src/templates/preferences.html
  - src/scorer.py, src/scraper.py, src/models.py, src/alerts.py, src/main.py, src/config.py
  - README.md, .env.example, task_plan.md, progress.md

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Duunitori fetch | all search terms | ~500 jobs | 533 fetched | ✓ |
| The Hub fetch | countryCode=FI | Finland startup jobs | 53 fetched | ✓ |
| EnglishJobs.fi scrape | developer/data/software/engineer | English jobs | 76 fetched | ✓ |
| Total unique jobs stored | all sources | ~600+ | 661 stored | ✓ |
| Dashboard | GET / | HTML with jobs | 148KB rendered | ✓ |
| Preferences page | GET /preferences | form | rendered | ✓ |
| Save preferences | POST /preferences | redirect + re-score | 303 to / | ✓ |
| API jobs | GET /api/jobs | JSON array | returned ranked jobs | ✓ |
| Salary extraction | regex tests | structured salary | implemented | ✓ |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-07-04 18:43 | asyncio.run() in running event loop | 1 | AsyncIOScheduler + async lifespan |
| 2026-07-04 18:46 | NoneType lower | 1 | `or ""` fallbacks |
| 2026-07-04 19:55 | Jinja2 TemplateResponse signature | 1 | Pass request first |
| 2026-07-04 19:58 | No average filter | 1 | Compute in Python |
| 2026-07-04 21:25 | EnglishJobsSource missing normalize | 1 | Added normalize method |
| 2026-07-04 21:30 | The Hub country filter wrong | 1 | Use countryCode=FI |
| 2026-07-04 21:32 | Old SQLite schema | 1 | Recreate database |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 4 complete; all requested features delivered |
| Where am I going? | User review and further iterations |
| What's the goal? | Job-hunting agent for best junior tech positions in Finland |
| What have I learned? | See findings.md |
| What have I done? | See above |

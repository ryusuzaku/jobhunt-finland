# Task Plan: Finnish Junior Tech Job Hunting Agent

## Goal
Build and deliver a job-hunting agent that surfaces the best junior-level tech positions in Finland through a web dashboard and alert bot, scoring opportunities by learning/growth potential, work-life/location fit, tech-stack match, and company quality.

## Current Phase
Phase 3 (more sources)

## Phases

### Phase 1: Requirements & Discovery
- [x] Capture initial user intent
- [x] Clarify scope, success criteria, and user preferences
- [x] Research Finnish junior tech job landscape and source websites
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Planning & Architecture
- [x] Define agent capabilities (aggregate, filter, score, dashboard, alerts)
- [x] Choose technical stack and delivery format
- [x] Design data model and scoring/ranking logic
- [x] Select MVP data source and access method
- **Status:** complete

### Phase 3: Expanded MVP Implementation
- [x] Core Duunitori ingestion + scoring + dashboard
- [x] Add The Hub source
- [x] Add EnglishJobs.fi source
- [x] Document LinkedIn / WorkinFinland limitations
- [x] Editable preferences in dashboard
- [x] Discord/Slack webhook alerts
- [x] Improved salary extraction
- [x] Company-level signals
- [ ] Add Jobly/Monster source
- [ ] Add Academic Work source
- **Status:** in_progress

### Phase 4: Testing & Delivery
- [ ] Verify new sources work
- [ ] Update documentation
- [ ] Deliver to user
- **Status:** pending

## Key Decisions from User
| Decision | User Choice |
|----------|-------------|
| "Best" ranking criteria | Learning & growth first, work-life/location, tech-stack match |
| Delivery format | Web dashboard + alert bot |
| Target roles | Software/web dev, data/AI/ML, all junior tech roles (broad coverage) |
| Immediate action | Build MVP, then add enhancements, then add more sources |

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Python + FastAPI + SQLite | Fast MVP, zero-config persistence, async-friendly |
| Duunitori + The Hub + EnglishJobs.fi + Jobly + Academic Work | Best balance of coverage and reliability |
| Indeed/Oikotie/JobsinHelsinki/JobsinFinland/LinkedIn excluded | Blocked, JS-rendered, duplicated, or ToS-blocked |
| Jinja2 server-rendered dashboard | No frontend build step |
| Heuristic scoring | Transparent, no ML needed |
| Console/email + webhook alerts | Flexible notification options |
| Company signals from The Hub | Rich company metadata (size, founded, perks) |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (See previous plan versions) | | |

## Notes
- Need to respect robots.txt and terms of service for every source.
- Detail-page scraping is capped to avoid overloading source sites.

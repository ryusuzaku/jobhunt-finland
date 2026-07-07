# Findings & Decisions

## Requirements
- Build/plan a job-hunting agent for junior-level positions in the Finnish tech field.
- Current job websites are perceived as poor at surfacing the best opportunities.
- Goal: get the best possible junior positions available.

### Clarified Requirements (from user Q&A)
- **Ranking priorities:** Learning & growth first, then work-life/location fit, then tech-stack match.
- **Delivery format:** Web dashboard + alert bot.
- **Target roles:** Broad coverage — software/web dev, data/AI/ML, and all other junior tech roles.
- **Scope:** Build a working MVP, then add all suggested enhancements, then add more sources.

## Research Findings
### Finnish Junior Tech Job Market (2025)
- **Tough market for juniors:** Duunitori/Helsinki Times report an oversupply of junior/generalist developers, while experienced specialists (AI/ML, data engineering, cloud, cybersecurity, SRE) remain in demand.
- **Job ad volume:** ICT job ads Jan-Aug 2025 down ~16% YoY in Uusimaa (still the largest region, ~3,450 ads). Pirkanmaa (~540, +4%) and Northern Ostrobothnia (~210, +7%) growing.
- **Salary expectations:** Junior/early-career developers typically earn €3,000–€4,000/month. Traineeships can vary significantly.
- **Top in-demand skills** for junior/remote dev roles: JavaScript, TypeScript, CI/CD, Git, Docker, React, C#, CSS, Python, SQL.
- **Hiring timeline:** Remote junior roles take ~44 days to close on average.

### Candidate Data Sources
| Source | Type | Notes |
|--------|------|-------|
| **Duunitori API v1** | JSON API | `https://duunitori.fi/api/v1/jobentries?search=...&format=json`; paginated; covers most Finnish listings. |
| **The Hub** | JSON API | `https://thehub.io/api/jobs?countryCode=FI`; rich company metadata. |
| **EnglishJobs.fi** | HTML scrape | `div.job` cards; English-speaking roles. |
| **Jobly / Monster** | HTML scrape | Jobly uses Monster backend; search pages server-rendered, detail pages parseable. |
| **Academic Work** | HTML scrape | Search + detail pages; many junior/trainee roles in Finland. |
| **Indeed Finland** | Blocked | Returns 403/Cloudflare security challenge. |
| **Oikotie** | JS-rendered | Short initial HTML; jobs loaded client-side. |
| **JobsinHelsinki** | JS-rendered | Homepage is landing page; listings loaded dynamically. |
| **JobsinFinland** | Duunitori aggregator | Links redirect to Duunitori; high duplication. |
| **LinkedIn** | Restricted | Scraping violates ToS. |

### Pain Points to Address
- Noise from senior roles mis-tagged as junior.
- Duplicate postings across boards.
- Many "junior" roles still require 2+ years of experience.
- Salary and language requirements often unclear.
- Best roles may not appear on the biggest boards.
- Hard to filter by true entry-level friendliness, mentorship quality, or tech stack.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Python + FastAPI + SQLite | Fast MVP, zero-config persistence, async-friendly |
| Multi-source ingestion (API + scraping) | Maximizes coverage while respecting technical limits |
| Headless-browser sources excluded | WorkinFinland/Oikotie/Indeed require heavy deps or proxies |
| Jinja2 server-rendered dashboard | No frontend build step |
| Heuristic scoring | Transparent, no ML needed |
| Console/email + webhook alerts | Flexible notification options |
| Detail-page scraping limited | Avoid hammering source sites; capped results per source |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| None yet | - |

## Resources
- Witted salary blog: https://witted.com/blog/developing/the-salary-level-of-software-developers-in-finland-in-2025
- The Hub API: `https://thehub.io/api/jobs?countryCode=FI`
- EnglishJobs.fi: https://englishjobs.fi/jobs/developer
- Finnish Dev Job API repo: https://github.com/it-ankka/dev-job-api
- Duunitori API endpoint pattern: `https://duunitori.fi/api/v1/jobentries?search=<term>&search_also_descr=1&format=json`

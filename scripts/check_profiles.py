# Unit-style checks for job profiles + scorer personalization (UTF-8 file to
# avoid PowerShell argv encoding mangling Finnish characters).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.job_profiles import (
    JOB_PROFILES,
    fi_search_terms,
    has_non_tech,
    in_search_terms,
    keep_job,
    linkedin_terms,
    skill_presets_for,
)

assert keep_job("Digital Marketing Specialist", "", ["marketing"])
assert keep_job("Markkinointipäällikkö", "", ["marketing"])
assert keep_job("Viestintäasiantuntija", "", ["marketing"])
assert not keep_job("Salesforce Developer", "", ["sales"])
assert keep_job("Backend Developer", "", ["software"])
assert keep_job("Myyntiedustaja", "", ["sales"])
assert keep_job("Account Manager", "", ["sales"])
assert keep_job("Kirjanpitäjä", "", ["finance"])
assert keep_job("Sairaanhoitaja", "", ["healthcare"])
assert keep_job("Luokanopettaja", "", ["education"])
assert keep_job("Varastotyöntekijä", "", ["logistics"])
assert keep_job("Sähköasentaja", "", ["electrical"])
assert keep_job("Keittiöapulainen", "", ["hospitality"])
assert not keep_job("Junior Python Developer", "", ["marketing"])
assert keep_job("Junior Developer", "backend api work", ["software"])
assert keep_job("Anything At All", "", [])
assert not keep_job("UX Designer", "", ["marketing"])
assert keep_job("UX Designer", "", ["design"])
assert not keep_job("Sales Engineer", "", ["marketing"])
assert keep_job("Sales Engineer", "", ["sales"])

t = fi_search_terms(["marketing", "finance"])
assert "markkinointi" in t and "kirjanpitäjä" in t and "junior developer" not in t, t
lt = linkedin_terms(["software", "frontend", "data", "devops", "mobile", "qa", "security", "marketing", "sales"])
assert len(lt) <= 8, len(lt)
assert in_search_terms(["marketing"]) == ["digital marketing", "marketing executive", "content writer", "seo"]
assert "seo" in skill_presets_for(["marketing"])
assert has_non_tech(["marketing"]) and not has_non_tech(["software", "design"])
print("job_profiles checks PASSED —", len(JOB_PROFILES), "profiles")

from src.scorer import score_job

base = {"preferred_tech": ["seo"], "preferred_locations": ["helsinki"], "remote_ok": True, "hybrid_ok": True}
a = score_job("Digital Marketing Trainee", "seo content google analytics", "Helsinki", dict(base))
b = score_job("Digital Marketing Trainee", "seo content google analytics", "Helsinki", dict(base, job_profiles=["marketing"]))
assert b["score"] > a["score"], (a["score"], b["score"])
c = score_job("Software Developer", "python", "Helsinki", dict(base, role_tracks=["software"]))
d = score_job("Software Developer", "python", "Helsinki", dict(base))
assert c["score"] > d["score"]
print("scorer checks PASSED (marketing bonus:", a["score"], "->", b["score"], ")")

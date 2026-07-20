"""Smoke-test the new sources without touching the DB."""
import asyncio
import sys

import httpx

sys.path.insert(0, ".")

from src.sources.hasjob import HasjobSource
from src.sources.shine import ShineSource
from src.sources.internshala import InternshalaSource
from src.sources.companycareers import CompanyCareersSource
from src.scorer import extract_salary


def show(source_name, jobs):
    print(f"\n=== {source_name}: {len(jobs)} jobs")
    for j in jobs[:3]:
        print(
            " -",
            j.get("title"),
            "|",
            j.get("company"),
            "|",
            j.get("location"),
            "|",
            j.get("salary_text"),
            "|",
            j.get("date_posted"),
        )


async def main():
    # Salary extraction sanity checks
    for sample in [
        "4.0 - 8 LPA",
        "₹ 3,00,000 - 5,00,000 /year",
        "₹ 15,000 /month",
        "1.8 LPA - 11.7 LPA",
        "3000-4000 €/kk",
    ]:
        print("salary:", repr(sample), "->", extract_salary(sample))

    sources = [HasjobSource(), ShineSource(), InternshalaSource(), CompanyCareersSource()]
    async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True) as client:
        for src in sources:
            try:
                raw = await src.fetch(client)
                normalized = []
                for item in raw:
                    norm = src.normalize(item)
                    if norm:
                        normalized.append(norm)
                show(src.name, normalized)
            except Exception as exc:
                print(f"\n=== {src.name} FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

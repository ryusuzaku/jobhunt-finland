"""Offline regression tests for job source adapters and salary parsing."""
from datetime import datetime
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from src.scorer import extract_salary
from src.sources.academicwork import AcademicWorkSource
from src.sources.jobly import JoblySource
from src.sources.thehub import TheHubSource


class SourceRegistryTests(unittest.TestCase):
    def test_all_fourteen_source_adapters_are_registered_once(self):
        from src.scraper import SOURCES

        names = [source.name for source in SOURCES]
        self.assertEqual(len(names), 14)
        self.assertEqual(len(set(names)), len(names))
        self.assertIn("jobly", names)
        self.assertIn("academicwork", names)


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, text: str):
        self.text = text

    async def get(self, url: str, **kwargs):
        return _FakeResponse(self.text)


class SourceAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_jobly_parses_listing_fields_and_date(self):
        markup = """
        <article class="node-job">
          <a class="recruiter-job-link" href="/en/job/123" title="Junior Software Developer">
            Junior Software Developer
          </a>
          <span>Posted 06.07.2026</span>
          <span>Example Oy, Helsinki</span>
        </article>
        """
        source = JoblySource()
        item = source._parse_row(BeautifulSoup(markup, "html.parser").article)

        self.assertIsNotNone(item)
        self.assertEqual(item["source"], "jobly")
        self.assertEqual(item["title"], "Junior Software Developer")
        self.assertEqual(item["url"], "https://www.jobly.fi/en/job/123")
        self.assertEqual(item["company"], "Example Oy")
        self.assertEqual(item["location"], "Helsinki")
        self.assertEqual(item["date_posted"], datetime(2026, 7, 6))

    def test_jobly_ignores_rows_without_a_recruiter_link(self):
        row = BeautifulSoup('<article class="node-job">No link</article>', "html.parser").article
        self.assertIsNone(JoblySource()._parse_row(row))

    def test_academic_work_extracts_unique_supported_job_links(self):
        markup = """
        <a href="/avoimet-tyopaikat/j/junior-developer/AB12CD">Role</a>
        <a href="/avoimet-tyopaikat/j/junior-developer/AB12CD">Duplicate</a>
        <a href="/avoimet-tyopaikat">Not a job detail page</a>
        """
        links = AcademicWorkSource()._extract_job_links(BeautifulSoup(markup, "html.parser"))
        self.assertEqual(links, ["https://www.academicwork.fi/avoimet-tyopaikat/j/junior-developer/AB12CD"])

    async def test_academic_work_parses_detail_page_without_network(self):
        markup = """
        <html><head><title>Junior Data Engineer</title></head>
        <body><h1>Junior Data Engineer, Helsinki</h1>
        <main>Hybrid work. Salary 3500 €/kk. Python and SQL.</main></body></html>
        """
        source = AcademicWorkSource()
        item = await source._fetch_detail(
            _FakeClient(markup),
            "https://www.academicwork.fi/avoimet-tyopaikat/j/data/AB12CD",
        )

        self.assertEqual(item["source"], "academicwork")
        self.assertEqual(item["title"], "Junior Data Engineer")
        self.assertEqual(item["company"], "Academic Work")
        self.assertEqual(item["location"], "Helsinki")
        self.assertTrue(item["hybrid"])
        self.assertEqual(item["salary_currency"], "EUR")
        self.assertEqual(item["salary_min"], 3500)
        self.assertIn("Python and SQL", item["description"])


class TheHubSourceTests(unittest.TestCase):
    def test_public_listing_extracts_title_company_location_and_next_page(self):
        html = '''<div class="card__content"><span class="card-job-find-list__position">Junior Backend Developer</span>
        <div class="bullet-inline-list"><span>Example Oy</span><span>Helsinki</span><span>Full-time</span></div>
        <a class="card-job-find-list__link" href="/jobs/abc123"></a></div>
        <a aria-label="Go to next page" href="?page=2">Next</a>'''
        jobs, next_page = TheHubSource._parse_listing(html)
        self.assertTrue(next_page)
        self.assertEqual(len(jobs), 1)
        normalized = TheHubSource().normalize(jobs[0])
        self.assertEqual(normalized['title'], 'Junior Backend Developer')
        self.assertEqual(normalized['company'], 'Example Oy')
        self.assertEqual(normalized['location'], 'Helsinki')
        self.assertEqual(normalized['url'], 'https://thehub.io/jobs/abc123')

    def test_legacy_endpoint_is_migrated_to_the_public_listing(self):
        from src.config import settings
        with patch.object(settings, 'thehub_base_url', 'https://thehub.io/api/jobs'):
            self.assertEqual(TheHubSource._make_url(2), 'https://thehub.io/jobs/location/finland?page=2')


class SalaryExtractionTests(unittest.TestCase):
    def test_finnish_monthly_salary(self):
        salary = extract_salary("3000-4000 €/kk")
        self.assertEqual((salary["min"], salary["max"], salary["currency"], salary["period"]),
                         (3000, 4000, "EUR", "month"))

    def test_indian_lpa_range(self):
        salary = extract_salary("4.0 - 8 LPA")
        self.assertEqual((salary["min"], salary["max"], salary["currency"], salary["period"]),
                         (400000, 800000, "INR", "year"))

    def test_unrecognized_salary_returns_none(self):
        self.assertIsNone(extract_salary("Salary negotiable"))


if __name__ == "__main__":
    unittest.main()

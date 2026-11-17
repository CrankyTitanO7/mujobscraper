"""Offline adapter tests using httpx mock transports."""

from __future__ import annotations

import json

import httpx

from jobscraper.sources.arbeitnow import ArbeitnowSource
from jobscraper.sources.config import SourcesConfig
from jobscraper.sources.generic import GenericSource
from jobscraper.sources.greenhouse import GreenhouseSource
from jobscraper.sources.jsonld import extract_jobs
from jobscraper.sources.lever import LeverSource
from jobscraper.sources.registry import build_sources
from jobscraper.sources.remoteok import RemoteOKSource
from jobscraper.utils.http import HttpClient


def mock_client(handler) -> HttpClient:
    return HttpClient(transport=httpx.MockTransport(handler), retries=0)


GREENHOUSE_DATA = {
    "jobs": [
        {
            "id": 123,
            "title": "Machine Learning Intern",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "location": {"name": "New York, NY"},
            "content": "<p>Build <strong>models</strong> with Python.</p>",
            "updated_at": "2026-01-02T03:04:05-05:00",
            "metadata": [
                {"name": "Employment Type", "value": "Internship"},
                {"name": "Department", "value": "AI"},
            ],
            "departments": [{"name": "Research"}],
        }
    ]
}


def test_greenhouse_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "boards-api.greenhouse.io" in str(request.url)
        return httpx.Response(200, json=GREENHOUSE_DATA)

    with mock_client(handler) as client:
        postings = GreenhouseSource(["acme"]).fetch(client)
    assert len(postings) == 1
    posting = postings[0]
    assert posting.title == "Machine Learning Intern"
    assert posting.company == "Acme"
    assert posting.location == "New York, NY"
    assert "Build" in posting.description
    assert "models" in posting.description
    assert posting.source == "greenhouse"
    assert posting.job_type == "internship"
    assert "AI" in posting.tags


LEVER_DATA = [
    {
        "id": "abc-123",
        "text": "Data Science Intern",
        "categories": {
            "location": "Remote",
            "team": "Data",
            "commitment": "Intern",
            "allLocations": ["Remote", "Boston"],
        },
        "descriptionPlain": "Analyze data with Python.",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
        "createdAt": 1767225600000,
    }
]


def test_lever_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.lever.co" in str(request.url)
        return httpx.Response(200, json=LEVER_DATA)

    with mock_client(handler) as client:
        postings = LeverSource(["acme"]).fetch(client)
    posting = postings[0]
    assert posting.title == "Data Science Intern"
    assert posting.company == "Acme"
    assert posting.location == "Remote"
    assert posting.apply_url.endswith("/apply")
    assert posting.source_id == "abc-123"
    assert posting.posted_at.startswith("2026-01-01")


ARBEITNOW_DATA = {
    "data": [
        {
            "slug": "ml-intern-acme",
            "company_name": "Acme",
            "title": "ML Intern",
            "description": "<p>Python and machine learning</p>",
            "remote": True,
            "url": "https://www.arbeitnow.com/view/ml-intern-acme",
            "tags": ["python", "ml"],
            "job_types": ["internship"],
            "location": "Berlin",
            "created_at": 1767225600,
        }
    ],
    "links": {"next": None},
}


def test_arbeitnow_source_and_search_filter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ARBEITNOW_DATA)

    with mock_client(handler) as client:
        postings = ArbeitnowSource(pages=1, search="python").fetch(client)
        assert len(postings) == 1
        assert postings[0].location == "Berlin"
        assert "remote" in postings[0].tags
        assert postings[0].job_type == "internship"
    with mock_client(handler) as client:
        assert ArbeitnowSource(pages=1, search="golang").fetch(client) == []


REMOTEOK_DATA = [
    {"legal": "See remoteok.com terms"},
    {
        "id": "999",
        "position": "Junior ML Engineer",
        "company": "Acme",
        "description": "<p>Remote ML work.</p>",
        "tags": ["python", "ml"],
        "url": "https://remoteok.com/remote-jobs/999",
        "apply_url": "https://remoteok.com/remote-jobs/999/apply",
        "location": "Worldwide",
        "date": "2026-01-02T03:04:05+00:00",
    },
]


def test_remoteok_source_filters_legal_notice_and_tags() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=REMOTEOK_DATA)

    with mock_client(handler) as client:
        postings = RemoteOKSource(tags=["python"]).fetch(client)
    assert len(postings) == 1
    assert postings[0].title == "Junior ML Engineer"
    assert postings[0].source_id == "999"
    with mock_client(handler) as client:
        assert RemoteOKSource(tags=["rust"]).fetch(client) == []


JSONLD_HTML = """
<html><head><script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Machine Learning Engineer",
  "datePosted": "2026-02-01",
  "employmentType": "FULL_TIME",
  "hiringOrganization": {"@type": "Organization", "name": "Acme"},
  "jobLocation": {"@type": "Place", "address": {
    "@type": "PostalAddress", "addressLocality": "Boston",
    "addressRegion": "MA", "addressCountry": "US"}},
  "description": "<p>Build models.</p>",
  "url": "https://example.com/jobs/1",
  "identifier": {"@type": "PropertyValue", "value": "job-1"}
}
</script></head><body></body></html>
"""


def test_jsonld_extraction() -> None:
    postings = extract_jobs(JSONLD_HTML, "https://example.com/jobs/1")
    assert len(postings) == 1
    posting = postings[0]
    assert posting.company == "Acme"
    assert posting.location == "Boston, MA, US"
    assert posting.job_type == "full_time"
    assert posting.source_id == "job-1"


def test_jsonld_graph_and_metadata_fallback() -> None:
    graph = json.dumps(
        {
            "@graph": [
                {"@type": "WebSite", "name": "Example"},
                {
                    "@type": "JobPosting",
                    "title": "Data Intern",
                    "hiringOrganization": {"name": "Example"},
                    "description": "Data work",
                },
            ]
        }
    )
    postings = extract_jobs(
        f'<script type="application/ld+json">{graph}</script>',
        "https://example.com/jobs/2",
    )
    assert [posting.title for posting in postings] == ["Data Intern"]
    fallback = extract_jobs(
        '<html><head><meta property="og:title" content="Research Intern">'
        '<meta property="og:site_name" content="Example">'
        '<meta property="og:description" content="Research things"></head></html>',
        "https://example.com/jobs/3",
    )
    assert fallback[0].title == "Research Intern"
    assert fallback[0].company == "Example"


def test_generic_source_uses_jsonld() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=JSONLD_HTML)

    with mock_client(handler) as client:
        postings = GenericSource(["https://example.com/jobs/1"]).fetch(client)
    assert postings[0].title == "Machine Learning Engineer"


def test_source_registry() -> None:
    config = SourcesConfig.model_validate(
        {
            "greenhouse": {"boards": ["acme"]},
            "lever": {"companies": ["beta"]},
            "arbeitnow": {"enabled": True, "pages": 2},
            "remoteok": {"enabled": False},
            "generic": {"urls": ["https://example.com/job"]},
        }
    )
    names = [source.name for source in build_sources(config, request_delay=0)]
    assert names == ["greenhouse", "lever", "arbeitnow", "generic"]

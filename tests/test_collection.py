"""Collection, deduplication, and re-filtering tests."""

from __future__ import annotations

import httpx
import pytest

from jobscraper.config import Config
from jobscraper.core.webscraper import collect_jobs, include_terms, refilter_jobs
from jobscraper.models import JobPosting, JobStatus
from jobscraper.sources.base import JobSource
from jobscraper.storage.jobs import JobStore
from jobscraper.utils.errors import ConfigError
from jobscraper.utils.http import HttpClient


class FakeSource(JobSource):
    name = "fake"

    def __init__(self, postings: list[JobPosting], name: str = "fake") -> None:
        self.postings = postings
        self.name = name

    def fetch(self, client: HttpClient) -> list[JobPosting]:
        return list(self.postings)


def dummy_client() -> HttpClient:
    return HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))


def posting(**overrides) -> JobPosting:
    values = {
        "title": "Machine Learning Intern",
        "company": "Acme",
        "source": "fake",
        "source_id": "1",
        "location": "Remote",
        "description": "Python and machine learning.",
        "url": "https://example.com/1",
        "apply_url": "https://example.com/1",
        "tags": ["python", "machine learning"],
        "job_type": "internship",
        "field": "Machine Learning",
    }
    values.update(overrides)
    return JobPosting(**values)


def test_include_terms_merge_extended_tags(config: Config) -> None:
    assert "internship" in include_terms(config)
    assert "remote" in include_terms(config)


def test_collect_filters_and_stores(config: Config, sources_config) -> None:
    source = FakeSource([posting(), posting(source_id="2", title="Senior ML Intern")])
    report = collect_jobs(
        config,
        sources_config,
        sources=[source],
        client=dummy_client(),
    )
    assert report.discovered == 2
    assert report.added == 2
    assert report.filtered_out == 1
    jobs = JobStore.from_config(config).load()
    assert {job.status for job in jobs} == {JobStatus.NEW, JobStatus.FILTERED_OUT}
    assert any("senior" in job.exclude_matches for job in jobs)


def test_collect_deduplicates_within_run(config: Config, sources_config) -> None:
    source = FakeSource([posting(), posting()])
    report = collect_jobs(config, sources_config, sources=[source], client=dummy_client())
    assert report.discovered == 1
    assert len(JobStore.from_config(config).load()) == 1


def test_collect_dry_run_writes_nothing(config: Config, sources_config) -> None:
    report = collect_jobs(
        config,
        sources_config,
        sources=[FakeSource([posting()])],
        client=dummy_client(),
        dry_run=True,
    )
    assert report.added == 1
    assert JobStore.from_config(config).load() == []


def test_collect_preserves_applied_status(config: Config, sources_config) -> None:
    from tests.conftest import make_job

    job = make_job(config, status=JobStatus.APPLIED)
    source = FakeSource(
        [
            posting(
                title=job.title,
                company=job.company,
                source="test",
                source_id="Acme-Machine Learning Intern",
            )
        ]
    )
    collect_jobs(config, sources_config, sources=[source], client=dummy_client())
    loaded = JobStore.from_config(config).require(job.job_id)
    assert loaded.status == JobStatus.APPLIED


def test_collect_limit(config: Config, sources_config) -> None:
    postings = [posting(source_id=str(index)) for index in range(5)]
    report = collect_jobs(
        config,
        sources_config,
        sources=[FakeSource(postings)],
        client=dummy_client(),
        limit=2,
    )
    assert report.discovered == 2


def test_collect_requires_a_source(config: Config, sources_config) -> None:
    with pytest.raises(ConfigError, match="No matching job sources"):
        collect_jobs(config, sources_config, sources=[], client=dummy_client())


def test_source_failure_is_reported(config: Config, sources_config) -> None:
    class BrokenSource(JobSource):
        name = "broken"

        def fetch(self, client: HttpClient) -> list[JobPosting]:
            raise RuntimeError("network down")

    report = collect_jobs(config, sources_config, sources=[BrokenSource()], client=dummy_client())
    assert report.discovered == 0
    assert "network down" in report.errors[0]


def test_refilter_restores_job_when_tags_change(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config, status=JobStatus.FILTERED_OUT)
    kept, filtered = refilter_jobs(config)
    assert kept == 1
    assert filtered == 0
    assert JobStore.from_config(config).require(job.job_id).status == JobStatus.NEW

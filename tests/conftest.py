"""Shared fixtures for offline tests."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from jobscraper.config import Config
from jobscraper.sources.config import SourcesConfig
from jobscraper.storage.applications import ApplicationStore
from jobscraper.storage.jobs import JobStore
from jobscraper.storage.questions import BankStore, QuestionStore

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

URLS_YAML = """\
greenhouse:
  enabled: true
  boards: []
lever:
  enabled: true
  companies: []
arbeitnow:
  enabled: false
  pages: 1
  search: ""
remoteok:
  enabled: false
  tags: []
generic:
  enabled: true
  urls: []
"""


class FakeProvider:
    """Scriptable LLM provider that records prompts."""

    name = "fake"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or ["A tailored answer."])
        self.prompts: list[tuple[str, str]] = []

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.prompts.append((system, prompt))
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    user = tmp_path / "user"
    user.mkdir()
    shutil.copyfile(REPO_ROOT / "user" / "user.example.toml", user / "user.toml")
    (user / "urls.yaml").write_text(URLS_YAML, encoding="utf-8")
    (user / "extendedTags.yaml").write_text("extendedTags:\n  - remote\n", encoding="utf-8")
    (user / "resume.md").write_text(
        "# Test Candidate\nPython and machine learning experience.\n", encoding="utf-8"
    )
    config = Config.load(tmp_path)
    config.ensure_directories()
    JobStore.from_config(config).ensure()
    ApplicationStore.from_config(config).ensure()
    QuestionStore.from_config(config).ensure()
    BankStore.from_config(config).ensure()
    return tmp_path


@pytest.fixture
def config(project_root: Path) -> Config:
    return Config.load(project_root)


@pytest.fixture
def sources_config() -> SourcesConfig:
    return SourcesConfig.model_validate(
        {
            "greenhouse": {"boards": []},
            "lever": {"companies": []},
            "arbeitnow": {"enabled": False},
            "remoteok": {"enabled": False},
            "generic": {"urls": []},
        }
    )


@pytest.fixture
def sample_form_html() -> str:
    return (FIXTURES / "sample_form.html").read_text(encoding="utf-8")


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


def make_job(
    config: Config,
    *,
    title: str = "Machine Learning Intern",
    company: str = "Acme",
    description: str = "Work on Python and machine learning.",
    tags: list[str] | None = None,
    status: Any = None,
    apply_url: str = "https://example.com/apply",
):
    from jobscraper.models import JobPosting
    from jobscraper.storage.jobs import JobStore

    posting = JobPosting(
        title=title,
        company=company,
        source="test",
        source_id=f"{company}-{title}",
        location="Remote",
        description=description,
        url=apply_url,
        apply_url=apply_url,
        tags=tags or ["python", "machine learning"],
        job_type="internship",
        field="Machine Learning",
    )
    store = JobStore.from_config(config)
    job = store._from_row(
        {
            "job_id": posting.job_id,
            "status": (status.value if status else "new"),
            "title": title,
            "company": company,
            "location": posting.location,
            "job_type": posting.job_type,
            "field": posting.field,
            "source": posting.source,
            "source_id": posting.source_id,
            "url": posting.url,
            "apply_url": posting.apply_url,
            "tags": "; ".join(posting.tags),
        }
    )
    jobs = store.load()
    jobs = [existing for existing in jobs if existing.job_id != job.job_id]
    jobs.append(job)
    store.save_all(jobs)
    job.description_path = store.write_description(job.job_id, description)
    jobs = store.load()
    for item in jobs:
        if item.job_id == job.job_id:
            item.description_path = job.description_path
    store.save_all(jobs)
    return job

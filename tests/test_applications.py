"""Application packet and tracking tests."""

from __future__ import annotations

import pytest

from jobscraper.config import Config
from jobscraper.core.questionSubmit import (
    generate_packet,
    render_packet,
    track_application,
    update_application,
)
from jobscraper.models import ApplicationStatus, JobStatus, Question, QuestionStatus
from jobscraper.storage.applications import ApplicationStore
from jobscraper.storage.jobs import JobStore
from jobscraper.storage.questions import QuestionStore
from jobscraper.utils.errors import DataError


def add_question(
    config: Config, job_id: str, status: QuestionStatus = QuestionStatus.APPROVED
) -> Question:
    from jobscraper.models import AnswerKind

    question = Question.create(
        job_id=job_id,
        question="Why this role?",
        normalized="why this role",
        kind=AnswerKind.FREE_TEXT,
    )
    question.answer = "Because of the mission."
    question.status = status
    store = QuestionStore.from_config(config)
    store.save_all([*store.load(), question])
    return question


def test_render_packet_contains_answers_and_review_warning(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    question = add_question(config, job.job_id)
    text = render_packet(config, job, "Description here", [question])
    assert "Machine Learning Intern" in text
    assert "Acme" in text
    assert "Because of the mission." in text
    assert "never submits" in text
    assert question.question_id in text


def test_generate_packet_writes_file_and_marks_ready(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    add_question(config, job.job_id)
    path = generate_packet(config, job.job_id)
    assert path.is_file()
    assert path.name == "application.md"
    assert "## Submission checklist" in path.read_text(encoding="utf-8")
    loaded = JobStore.from_config(config).require(job.job_id)
    assert loaded.status == JobStatus.PACKET_READY
    assert loaded.packet_path


def test_packet_with_pending_question_does_not_advance_status(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    add_question(config, job.job_id, status=QuestionStatus.UNANSWERED)
    generate_packet(config, job.job_id)
    assert JobStore.from_config(config).require(job.job_id).status == JobStatus.NEW


def test_track_application_creates_history_and_updates_job(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    application = track_application(config, job.job_id)
    assert application.status == ApplicationStatus.APPLIED
    assert application.season == "2026"
    loaded_job = JobStore.from_config(config).require(job.job_id)
    assert loaded_job.status == JobStatus.APPLIED
    assert loaded_job.applied_at
    applications = ApplicationStore.from_config(config).load()
    assert len(applications) == 1


def test_track_same_job_updates_instead_of_duplicating(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    first = track_application(config, job.job_id)
    second = track_application(
        config, job.job_id, status=ApplicationStatus.INTERVIEW, notes="Phone screen"
    )
    assert first.application_id == second.application_id
    assert second.status == ApplicationStatus.INTERVIEW
    assert "Phone screen" in second.notes
    assert len(ApplicationStore.from_config(config).load()) == 1


def test_duplicate_guard_for_same_company_and_title(config: Config) -> None:
    from tests.conftest import make_job

    first = make_job(config)
    track_application(config, first.job_id)
    second = make_job(config, description="A different posting.")
    second.source_id = "other"
    # make_job uses a deterministic id based on company/title; rebuild with a unique URL.
    from jobscraper.models import JobPosting

    posting = JobPosting(
        title=second.title,
        company=second.company,
        source="other",
        source_id="other-2",
        apply_url="https://example.com/other",
    )
    store = JobStore.from_config(config)
    jobs = [job for job in store.load() if job.job_id != second.job_id]
    from jobscraper.models import Job

    other = Job.from_posting(posting)
    jobs.append(other)
    store.save_all(jobs)
    with pytest.raises(DataError, match="already recorded"):
        track_application(config, other.job_id)
    forced = track_application(config, other.job_id, force=True)
    assert forced.job_id == other.job_id


def test_update_application_status(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    application = track_application(config, job.job_id)
    updated = update_application(
        config,
        application.application_id,
        status=ApplicationStatus.OFFER,
        notes="Offer received",
    )
    assert updated.status == ApplicationStatus.OFFER
    assert "Offer received" in updated.notes


def test_unknown_application_raises(config: Config) -> None:
    with pytest.raises(DataError, match="Unknown application"):
        update_application(config, "app_missing", status=ApplicationStatus.REJECTED)

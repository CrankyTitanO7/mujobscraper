"""CSV table round-trip and repository tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobscraper.config import Config
from jobscraper.models import (
    AnswerKind,
    ApplicationStatus,
    BankAnswer,
    BankStatus,
    JobStatus,
    Question,
    QuestionStatus,
)
from jobscraper.storage.applications import ApplicationStore
from jobscraper.storage.csv_store import CsvTable
from jobscraper.storage.jobs import JobStore
from jobscraper.storage.questions import BankStore, QuestionStore
from jobscraper.utils.errors import DataError


def test_csv_round_trip_preserves_custom_columns(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"
    table = CsvTable(path, ["id", "name"])
    table.write([{"id": "1", "name": "Ada", "custom": "kept"}])
    rows = table.read()
    assert rows == [{"id": "1", "name": "Ada", "custom": "kept"}]
    table.write(rows)
    assert "custom" in path.read_text(encoding="utf-8")


def test_csv_atomic_update_and_bom(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"
    path.write_text("\ufeffid,name\n1,Ada\n", encoding="utf-8")
    table = CsvTable(path, ["id", "name"])
    assert table.read() == [{"id": "1", "name": "Ada"}]
    table.write([{"id": "2", "name": "Grace"}])
    assert table.read() == [{"id": "2", "name": "Grace"}]
    assert not list(tmp_path.glob(".*.tmp"))


def test_job_store_round_trip_and_description(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    store = JobStore.from_config(config)
    loaded = store.require(job.job_id)
    assert loaded.company == "Acme"
    assert loaded.status == JobStatus.NEW
    assert "machine learning" in store.read_description(loaded)
    assert loaded.description_path.startswith("user/jobDetails/")


def test_job_store_rejects_unknown_status(config: Config) -> None:
    store = JobStore.from_config(config)
    table_path = config.resolve_path(config.paths.job_status_table)
    table_path.write_text(
        "job_id,status,title,company\njob_x,made_up,Role,Acme\n", encoding="utf-8"
    )
    with pytest.raises(DataError, match="unknown job status"):
        store.load()


def test_job_status_alias(config: Config) -> None:
    store = JobStore.from_config(config)
    table_path = config.resolve_path(config.paths.job_status_table)
    table_path.write_text(
        "job_id,status,title,company\njob_x,not started,Role,Acme\n", encoding="utf-8"
    )
    assert store.load()[0].status == JobStatus.NEW


def test_question_store_round_trip(config: Config) -> None:
    store = QuestionStore.from_config(config)
    question = Question.create(
        job_id="job_1",
        question="Are you authorized to work?",
        normalized="are you authorized to work",
        kind=AnswerKind.BOOLEAN,
        options=["Yes", "No"],
        source="test",
    )
    store.save_all([question])
    loaded = store.for_job("job_1")[0]
    assert loaded.kind == AnswerKind.BOOLEAN
    assert loaded.options == ["Yes", "No"]
    assert loaded.status == QuestionStatus.UNANSWERED


def test_bank_store_round_trip(config: Config) -> None:
    store = BankStore.from_config(config)
    answer = BankAnswer.create(
        question="Why this role?",
        normalized="why this role",
        answer="Because of {company}.",
        status=BankStatus.APPROVED,
    )
    store.save_all([answer])
    loaded = store.get(answer.answer_id)
    assert loaded is not None
    assert loaded.answer == "Because of {company}."
    assert store.approved()[0].answer_id == answer.answer_id


def test_application_duplicate_guard(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    store = ApplicationStore.from_config(config)
    application = store._from_row(
        {
            "application_id": "app_1",
            "job_id": job.job_id,
            "company": job.company,
            "title": job.title,
            "season": "2026",
            "status": ApplicationStatus.APPLIED.value,
        }
    )
    store.save_all([application])
    assert store.find_duplicate(company=job.company, title=job.title, season="2026")
    assert not store.find_duplicate(company=job.company, title=job.title, season="2027")

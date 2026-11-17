"""Question extraction, bank reuse, drafting, and approval tests."""

from __future__ import annotations

import pytest

from jobscraper.config import Config
from jobscraper.core.questionParse import (
    approve_question,
    best_bank_match,
    draft_answers,
    scan_questions,
    set_answer,
    skip_question,
)
from jobscraper.core.updateData import refresh_statuses
from jobscraper.models import (
    AnswerKind,
    BankAnswer,
    BankStatus,
    JobStatus,
    Question,
    QuestionStatus,
)
from jobscraper.storage.jobs import JobStore
from jobscraper.storage.questions import BankStore, QuestionStore
from jobscraper.utils.errors import DataError


def scan(config: Config, job_id: str, html: str, **kwargs):
    return scan_questions(config, job_id, html, **kwargs)


def by_ref(questions, ref: str):
    return next(question for question in questions if question.field_ref == ref)


def test_extract_sample_form_fields(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    refs = {question.field_ref: question for question in questions}
    assert "csrf" not in refs
    assert refs["full_name"].question == "Full name"
    assert refs["email"].kind == AnswerKind.FREE_TEXT
    assert refs["resume"].kind == AnswerKind.FILE
    assert refs["work_auth"].kind == AnswerKind.BOOLEAN
    assert refs["work_auth"].options == ["Yes", "No"]
    assert refs["sponsorship"].kind == AnswerKind.BOOLEAN
    assert refs["why"].kind == AnswerKind.FREE_TEXT
    assert refs["relocate"].kind == AnswerKind.BOOLEAN
    # The conftest resume exists, so file questions are ready.
    assert refs["resume"].status == QuestionStatus.APPROVED
    assert refs["resume"].answer.endswith("resume.md")


def test_bank_answer_is_reused_and_rendered(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    bank_store = BankStore.from_config(config)
    bank_store.save_all(
        [
            BankAnswer.create(
                question="Why are you interested in this role?",
                normalized="why are you interested in this role",
                answer="I want to join {company} and work as a {role}.",
                status=BankStatus.APPROVED,
                job_type="internship",
                job_field="Machine Learning",
            )
        ]
    )
    questions = scan(config, job.job_id, sample_form_html)
    why = by_ref(questions, "why")
    assert why.status == QuestionStatus.REUSED
    assert why.answer == "I want to join Acme and work as a Machine Learning Intern."
    assert why.answer_id
    assert why.confidence


def test_best_bank_match_respects_kind_and_threshold() -> None:
    boolean = BankAnswer.create(
        question="Are you authorized to work in the US?",
        normalized="are you authorized to work in the us",
        answer="true",
        kind=AnswerKind.BOOLEAN,
    )
    assert best_bank_match("Are you authorized to work in the US?", AnswerKind.BOOLEAN, [boolean])
    assert best_bank_match("Are you authorized to work in the US?", AnswerKind.FREE_TEXT, [boolean])
    assert not best_bank_match(
        "Are you authorized to work?", AnswerKind.MULTIPLE_CHOICE, [boolean], threshold=1.0
    )


def test_set_answer_updates_question_and_bank(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    full_name = by_ref(questions, "full_name")
    updated, bank = set_answer(config, full_name.question_id, "Big John")
    assert updated.status == QuestionStatus.APPROVED
    assert bank is not None
    assert bank.answer == "Big John"
    loaded_bank = BankStore.from_config(config).get(bank.answer_id)
    assert loaded_bank is not None
    assert loaded_bank.status == BankStatus.APPROVED


def test_boolean_answer_is_normalized_and_validated(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    work_auth = by_ref(questions, "work_auth")
    with pytest.raises(DataError, match="true/false"):
        set_answer(config, work_auth.question_id, "maybe")
    updated, bank = set_answer(config, work_auth.question_id, "Yes")
    assert updated.answer == "true"
    assert bank is not None
    assert bank.kind == AnswerKind.BOOLEAN


def test_multiple_choice_answer_must_match_options(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    question = Question.create(
        job_id=job.job_id,
        question="Which office?",
        normalized="which office",
        kind=AnswerKind.MULTIPLE_CHOICE,
        options=["Boston", "Remote"],
    )
    store = QuestionStore.from_config(config)
    store.save_all([question])
    with pytest.raises(DataError, match="Boston"):
        set_answer(config, question.question_id, "New York")
    updated, _ = set_answer(config, question.question_id, "remote")
    assert updated.answer == "Remote"


def test_skip_question(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    skipped = skip_question(config, questions[0].question_id)
    assert skipped.status == QuestionStatus.SKIPPED


def test_draft_answers_marks_needs_review(
    config: Config, sample_form_html: str, fake_provider
) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    for question in questions:
        if question.field_ref != "why":
            skip_question(config, question.question_id)
    fake_provider.responses = ["I am excited about applied machine learning at Acme."]
    drafted = draft_answers(config, job.job_id, provider=fake_provider)
    why = by_ref(drafted, "why")
    assert why.status == QuestionStatus.NEEDS_REVIEW
    assert "Acme" in fake_provider.prompts[0][1]
    assert why.answer.startswith("I am excited")


def test_draft_unknown_keeps_question_unanswered(
    config: Config, sample_form_html: str, fake_provider
) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    for question in questions:
        if question.field_ref != "why":
            skip_question(config, question.question_id)
    fake_provider.responses = ["[[UNKNOWN]]"]
    drafted = draft_answers(config, job.job_id, provider=fake_provider)
    assert by_ref(drafted, "why").status == QuestionStatus.UNANSWERED


def test_ai_refinement_overrides_labels(
    config: Config, sample_form_html: str, fake_provider
) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    fake_provider.responses = [
        '[{"field_ref": "full_name", "question": "What is your legal name?", '
        '"kind": "free_text", "options": []}, '
        '{"field_ref": "why", "question": "Why do you want this internship?", '
        '"kind": "free_text", "options": []}]'
    ]
    questions = scan(config, job.job_id, sample_form_html, use_ai=True, provider=fake_provider)
    refs = {question.field_ref for question in questions}
    assert refs == {"full_name", "why"}
    assert by_ref(questions, "full_name").question == "What is your legal name?"


def test_all_questions_answered_updates_job_status(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    for question in questions:
        if question.kind == AnswerKind.BOOLEAN:
            set_answer(config, question.question_id, "true")
        elif question.kind == AnswerKind.FILE:
            continue
        else:
            set_answer(config, question.question_id, "Answer")
    refreshed = JobStore.from_config(config).require(job.job_id)
    assert refreshed.status == JobStatus.ANSWERED


def test_approve_requires_answer(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan(config, job.job_id, sample_form_html)
    why = by_ref(questions, "why")
    with pytest.raises(DataError, match="no answer"):
        approve_question(config, why.question_id)


def test_refresh_statuses_without_questions_keeps_new(config: Config) -> None:
    from tests.conftest import make_job

    make_job(config)
    assert refresh_statuses(config)[0].status == JobStatus.NEW

"""Form mapping tests plus an opt-in local browser integration test."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jobscraper.browser.autofill import (
    FillAction,
    FillPlan,
    _apply_plan,
    autofill_job,
    build_fill_plan,
)
from jobscraper.browser.forms import extract_fields_from_html
from jobscraper.config import Config
from jobscraper.core.questionParse import scan_questions, set_answer
from jobscraper.models import AnswerKind, JobStatus
from jobscraper.storage.jobs import JobStore
from jobscraper.storage.questions import QuestionStore
from jobscraper.utils.errors import BrowserError

FIXTURE_FORM = Path(__file__).resolve().parent / "fixtures" / "sample_form.html"


def answers() -> dict[str, str]:
    return {
        "full_name": "Big John",
        "email": "bigjohn@example.com",
        "phone": "555-0100",
        "work_auth": "Yes",
        "sponsorship": "No",
        "why": "I want to build useful machine learning systems.",
        "relocate": "true",
    }


def prepare(config: Config, html: str) -> tuple[str, list]:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan_questions(config, job.job_id, html)
    by_ref = {question.field_ref: question for question in questions}
    for ref, answer in answers().items():
        set_answer(config, by_ref[ref].question_id, answer)
    return job.job_id, QuestionStore.from_config(config).for_job(job.job_id)


def plan_by_ref(plans: list[FillPlan], ref: str) -> FillPlan:
    return next(plan for plan in plans if plan.field.field_ref == ref)


def test_extract_fields_skips_hidden_and_identifies_kinds(sample_form_html: str) -> None:
    fields = {field.field_ref: field for field in extract_fields_from_html(sample_form_html)}
    assert "csrf" not in fields
    assert fields["full_name"].label == "Full name"
    assert fields["resume"].kind == AnswerKind.FILE
    assert fields["work_auth"].kind == AnswerKind.BOOLEAN
    assert fields["sponsorship"].options == ["Yes", "No"]
    assert fields["relocate"].kind == AnswerKind.BOOLEAN
    assert fields["relocate"].options == []


def test_build_fill_plan_maps_every_control(config: Config, sample_form_html: str) -> None:
    job_id, questions = prepare(config, sample_form_html)
    fields = extract_fields_from_html(sample_form_html)
    plans = build_fill_plan(fields, questions, resume_path=config.resume_path)
    assert plan_by_ref(plans, "full_name").action == FillAction.FILL
    assert plan_by_ref(plans, "full_name").answer == "Big John"
    assert plan_by_ref(plans, "resume").action == FillAction.UPLOAD
    assert plan_by_ref(plans, "work_auth").action == FillAction.CHECK
    work_auth = plan_by_ref(plans, "work_auth")
    assert work_auth.target_indices == [work_auth.field.option_indices[0]]
    assert plan_by_ref(plans, "sponsorship").action == FillAction.SELECT
    assert plan_by_ref(plans, "why").action == FillAction.FILL
    relocate = plan_by_ref(plans, "relocate")
    assert relocate.action == FillAction.CHECK
    assert relocate.target_indices == [relocate.field.control_indices[0]]


def test_needs_review_answer_requires_include_drafts(config: Config, sample_form_html: str) -> None:
    job_id, questions = prepare(config, sample_form_html)
    full_name = next(question for question in questions if question.field_ref == "full_name")
    set_answer(config, full_name.question_id, "Draft name", approve=False)
    questions = QuestionStore.from_config(config).for_job(job_id)
    fields = extract_fields_from_html(sample_form_html)
    plans = build_fill_plan(fields, questions, resume_path=config.resume_path)
    assert plan_by_ref(plans, "full_name").action == FillAction.SKIP
    plans = build_fill_plan(fields, questions, resume_path=config.resume_path, include_drafts=True)
    assert plan_by_ref(plans, "full_name").action == FillAction.FILL


def test_missing_answer_is_skipped(config: Config, sample_form_html: str) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan_questions(config, job.job_id, sample_form_html)
    fields = extract_fields_from_html(sample_form_html)
    plans = build_fill_plan(fields, questions, resume_path=config.resume_path)
    assert plan_by_ref(plans, "why").action == FillAction.SKIP
    assert "unanswered" in plan_by_ref(plans, "why").reason


def _launch(playwright):
    executable = shutil.which("chromium-browser") or shutil.which("chromium")
    kwargs = {"headless": True}
    if executable:
        kwargs["executable_path"] = executable
    try:
        return playwright.chromium.launch(**kwargs)
    except Exception as exc:  # noqa: BLE001 - integration test skips without a browser
        pytest.skip(f"Chromium unavailable: {exc}")


@pytest.mark.integration
def test_playwright_fills_form_without_submitting(config: Config, sample_form_html: str) -> None:
    from playwright.sync_api import sync_playwright

    job_id, questions = prepare(config, sample_form_html)
    fields = extract_fields_from_html(sample_form_html)
    plans = build_fill_plan(fields, questions, resume_path=config.resume_path)
    uri = FIXTURE_FORM.as_uri()
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        page = browser.new_page()
        try:
            page.goto(uri)
            for plan in plans:
                _apply_plan(page, plan)
            assert page.input_value("#full_name") == "Big John"
            assert page.input_value("#email") == "bigjohn@example.com"
            assert page.input_value("#phone") == "555-0100"
            assert page.is_checked("input[name=work_auth][value=yes]")
            assert page.input_value("#sponsorship") == "no"
            assert page.input_value("#why").startswith("I want to build")
            assert page.is_checked("input[name=relocate]")
            assert page.locator("#resume").evaluate("el => el.files.length") == 1
            assert page.url == uri  # no navigation, hence no submit click
        finally:
            browser.close()
    assert JobStore.from_config(config).require(job_id).status == JobStatus.ANSWERED


@pytest.mark.integration
def test_autofill_job_end_to_end(config: Config, sample_form_html: str, tmp_path: Path) -> None:
    job_id, _ = prepare(config, sample_form_html)
    screenshot = tmp_path / "form.png"
    report = autofill_job(
        config,
        job_id,
        url=FIXTURE_FORM.as_uri(),
        headless=True,
        fill=True,
        keep_open=False,
        screenshot=screenshot,
    )
    assert report.applied == 8
    assert report.skipped == 0
    assert screenshot.is_file()


def test_autofill_requires_url(config: Config) -> None:
    from tests.conftest import make_job

    job = make_job(config, apply_url="")
    with pytest.raises(BrowserError, match="No application URL"):
        autofill_job(config, job.job_id, url="", headless=True, fill=True, keep_open=False)

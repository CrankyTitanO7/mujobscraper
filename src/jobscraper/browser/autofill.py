"""Map saved answers onto form controls and fill them in a browser.

Submission is deliberately never automated. The browser is left open for the
user to review and click the final button themselves.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from dataclasses import field as dc_field
from enum import StrEnum
from pathlib import Path

from ..config import Config
from ..models import AnswerKind, Question, QuestionStatus
from ..storage.jobs import JobStore
from ..storage.questions import QuestionStore
from ..utils.errors import BrowserError
from ..utils.matching import normalize_question, question_similarity
from .forms import FormField, extract_fields_from_html

log = logging.getLogger(__name__)

FORM_MATCH_THRESHOLD = 0.62
USABLE_STATUSES = {QuestionStatus.APPROVED, QuestionStatus.REUSED}


class FillAction(StrEnum):
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UPLOAD = "upload"
    SKIP = "skip"


@dataclass(slots=True)
class FillPlan:
    field: FormField
    action: FillAction
    answer: str = ""
    target_indices: list[int] = dc_field(default_factory=list)
    question: Question | None = None
    reason: str = ""
    applied: bool = False

    @property
    def label(self) -> str:
        return self.field.label


@dataclass(slots=True)
class AutofillReport:
    url: str
    plans: list[FillPlan]
    screenshot: str = ""
    saved_questions: int = 0

    @property
    def applied(self) -> int:
        return sum(1 for plan in self.plans if plan.applied)

    @property
    def skipped(self) -> int:
        return sum(1 for plan in self.plans if plan.action == FillAction.SKIP)


def find_question_for_field(
    field: FormField, questions: list[Question]
) -> tuple[Question | None, float]:
    """Match by saved field reference first, then by label similarity."""
    ref = field.field_ref.casefold()
    for question in questions:
        if question.field_ref and question.field_ref.casefold() == ref:
            return question, 1.0
    best: tuple[Question | None, float] = (None, 0.0)
    for question in questions:
        score = question_similarity(field.label, question.question)
        if score > best[1]:
            best = (question, score)
    if best[1] >= FORM_MATCH_THRESHOLD:
        return best
    return None, best[1]


def build_fill_plan(
    fields: list[FormField],
    questions: list[Question],
    *,
    resume_path: Path | None = None,
    include_drafts: bool = False,
) -> list[FillPlan]:
    """Create a deterministic plan; nothing is filled here."""
    plans: list[FillPlan] = []
    for form_field in fields:
        question, score = find_question_for_field(form_field, questions)
        if form_field.looks_like_resume:
            if resume_path and resume_path.is_file():
                plans.append(
                    FillPlan(
                        field=form_field,
                        action=FillAction.UPLOAD,
                        answer=str(resume_path),
                        target_indices=form_field.control_indices,
                        question=question,
                    )
                )
            else:
                plans.append(
                    FillPlan(
                        field=form_field,
                        action=FillAction.SKIP,
                        question=question,
                        reason="Resume file is not available",
                    )
                )
            continue
        if question is None:
            plans.append(
                FillPlan(
                    field=form_field,
                    action=FillAction.SKIP,
                    reason="No matching saved question",
                )
            )
            continue
        if question.status not in USABLE_STATUSES and not (
            include_drafts and question.status == QuestionStatus.NEEDS_REVIEW
        ):
            plans.append(
                FillPlan(
                    field=form_field,
                    action=FillAction.SKIP,
                    question=question,
                    reason=f"Answer status is {question.status.value}",
                )
            )
            continue
        if form_field.kind == AnswerKind.FILE:
            if question.answer and Path(question.answer).is_file():
                plans.append(
                    FillPlan(
                        field=form_field,
                        action=FillAction.UPLOAD,
                        answer=question.answer,
                        target_indices=form_field.control_indices,
                        question=question,
                    )
                )
            elif resume_path and resume_path.is_file():
                plans.append(
                    FillPlan(
                        field=form_field,
                        action=FillAction.UPLOAD,
                        answer=str(resume_path),
                        target_indices=form_field.control_indices,
                        question=question,
                    )
                )
            else:
                plans.append(
                    FillPlan(
                        field=form_field,
                        action=FillAction.SKIP,
                        question=question,
                        reason="No resume file",
                    )
                )
            continue
        answer = question.answer.strip()
        if not answer:
            plans.append(
                FillPlan(
                    field=form_field,
                    action=FillAction.SKIP,
                    question=question,
                    reason="Saved answer is empty",
                )
            )
            continue
        plan = _plan_answer(form_field, question, answer)
        if score < 1.0:
            plan.reason = f"Matched by label (score {score:.2f})"
        plans.append(plan)
    return plans


def _plan_answer(form_field: FormField, question: Question, answer: str) -> FillPlan:
    if form_field.input_type == "select":
        choice = _choice_index(form_field, answer)
        if choice is None:
            return FillPlan(
                field=form_field,
                action=FillAction.SKIP,
                question=question,
                answer=answer,
                reason="Answer does not match a select option",
            )
        return FillPlan(
            field=form_field,
            action=FillAction.SELECT,
            answer=form_field.options[choice],
            question=question,
        )
    if form_field.input_type in {"radio", "checkbox"} and form_field.options:
        selected = _selected_indices(form_field, answer)
        if not selected:
            return FillPlan(
                field=form_field,
                action=FillAction.SKIP,
                question=question,
                answer=answer,
                reason="Answer does not match an option",
            )
        return FillPlan(
            field=form_field,
            action=FillAction.CHECK,
            answer=answer,
            target_indices=selected,
            question=question,
        )
    if form_field.input_type == "checkbox":
        truthy = answer.strip().casefold() in {"true", "yes", "y", "1"}
        return FillPlan(
            field=form_field,
            action=FillAction.CHECK,
            answer="true" if truthy else "false",
            target_indices=form_field.control_indices if truthy else [],
            question=question,
        )
    return FillPlan(
        field=form_field,
        action=FillAction.FILL,
        answer=answer,
        target_indices=form_field.control_indices,
        question=question,
    )


def _choice_index(form_field: FormField, answer: str) -> int | None:
    normalized = normalize_question(answer)
    for index, option in enumerate(form_field.options):
        if normalize_question(option) == normalized:
            return index
    if form_field.kind == AnswerKind.BOOLEAN:
        truth = answer.strip().casefold() in {"true", "yes", "y", "1"}
        preferred = {"true": {"yes", "true", "y"}, "false": {"no", "false", "n"}}[
            "true" if truth else "false"
        ]
        for index, option in enumerate(form_field.options):
            if normalize_question(option) in preferred:
                return index
    return None


def _selected_indices(form_field: FormField, answer: str) -> list[int]:
    index = _choice_index(form_field, answer)
    return [form_field.option_indices[index]] if index is not None else []


def autofill_job(
    config: Config,
    job_id: str,
    *,
    url: str = "",
    headless: bool | None = None,
    fill: bool = False,
    keep_open: bool | None = None,
    screenshot: Path | None = None,
    save_questions: bool = False,
    include_drafts: bool | None = None,
    timeout_ms: int | None = None,
) -> AutofillReport:
    """Open an application page, plan/fill answers, and never submit."""
    job_store = JobStore.from_config(config)
    job = job_store.require(job_id)
    target_url = (url or job.apply_url or job.url).strip()
    if not target_url:
        raise BrowserError("No application URL. Pass --url or add one to the job row.")
    headless = config.autofill.headless if headless is None else headless
    keep_open = config.autofill.keep_open if keep_open is None else keep_open
    include_drafts = config.autofill.include_drafts if include_drafts is None else include_drafts
    timeout_ms = timeout_ms or config.autofill.timeout_ms
    executable = (
        config.autofill.browser_executable or os.environ.get("JOBSCRAPER_BROWSER_EXECUTABLE", "")
    ).strip()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise BrowserError("Playwright is not installed. Run `uv sync`.") from exc

    try:
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright, headless=headless, executable=executable)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:  # noqa: BLE001 - long-polling pages never go idle
                    pass
                html = page.content()
                saved = 0
                if save_questions:
                    from ..core.questionParse import scan_questions

                    saved = len(scan_questions(config, job_id, html, source="browser"))
                questions = QuestionStore.from_config(config).for_job(job_id)
                fields = extract_fields_from_html(html)
                plans = build_fill_plan(
                    fields,
                    questions,
                    resume_path=config.resume_path,
                    include_drafts=include_drafts,
                )
                if fill:
                    for plan in plans:
                        _apply_plan(page, plan)
                screenshot_path = ""
                if screenshot:
                    screenshot.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(screenshot), full_page=True)
                    screenshot_path = str(screenshot)
                if fill and keep_open and not headless and sys.stdin.isatty():
                    print(
                        "Form filled. Review it in the browser; press Enter to close (no submit)."
                    )
                    input()
                report = AutofillReport(
                    url=target_url,
                    plans=plans,
                    screenshot=screenshot_path,
                    saved_questions=saved,
                )
            finally:
                context.close()
                browser.close()
    except BrowserError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize Playwright/launch failures
        raise BrowserError(
            "Could not run browser autofill. Install Chromium with "
            "`uv run playwright install chromium`, or set [autofill].browser_executable.\n"
            f"Underlying error: {exc}"
        ) from exc
    return report


def _launch_browser(playwright: object, *, headless: bool, executable: str) -> object:
    """Launch managed Chromium, falling back to a detected system browser."""
    candidates: list[str | None] = [executable] if executable else [None]
    if not executable:
        for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
            found = shutil.which(name)
            if found and found not in candidates:
                candidates.append(found)
    errors: list[str] = []
    for candidate in candidates:
        kwargs: dict[str, object] = {"headless": headless}
        if candidate:
            kwargs["executable_path"] = candidate
        try:
            return playwright.chromium.launch(**kwargs)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            errors.append(f"{candidate or 'managed'}: {exc}")
    raise BrowserError(
        "Could not launch Chromium. Install it with `uv run playwright install chromium`, "
        "or set [autofill].browser_executable to a Chrome/Chromium binary.\n" + "\n".join(errors)
    )


def _apply_plan(page: object, plan: FillPlan) -> None:
    if plan.action == FillAction.SKIP:
        return
    try:
        locator_root = page.locator("input, textarea, select")  # type: ignore[attr-defined]
        if plan.action == FillAction.UPLOAD:
            target = locator_root.nth(plan.target_indices[0])
            target.set_input_files(plan.answer)
        elif plan.action == FillAction.SELECT:
            target = locator_root.nth(plan.field.control_indices[0])
            target.select_option(label=plan.answer)
        elif plan.action == FillAction.CHECK:
            for index in plan.target_indices:
                locator_root.nth(index).check()
            if not plan.target_indices:
                plan.reason = "Left unchecked (answer is false)"
        elif plan.action == FillAction.FILL:
            target = locator_root.nth(plan.field.control_indices[0])
            target.fill(plan.answer)
        else:  # pragma: no cover - exhaustive
            return
        plan.applied = True
    except Exception as exc:  # noqa: BLE001 - one bad control must not abort the form
        plan.reason = f"Fill failed: {exc}"
        log.warning("Could not fill %s: %s", plan.field.label, exc)


__all__ = [
    "AutofillReport",
    "FillAction",
    "FillPlan",
    "autofill_job",
    "build_fill_plan",
    "find_question_for_field",
]

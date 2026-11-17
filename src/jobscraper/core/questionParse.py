"""Extract application questions, reuse banked answers, and draft new ones."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace

from ..browser.forms import FormField, extract_fields_from_html
from ..config import Config
from ..llm.base import LLMProvider
from ..llm.factory import build_provider
from ..llm.prompts import build_answer_prompt, build_extraction_prompt, is_unknown, parse_json_array
from ..models import (
    AnswerKind,
    BankAnswer,
    BankStatus,
    Job,
    Question,
    QuestionStatus,
    isoformat,
    parse_answer_kind,
)
from ..storage.jobs import JobStore
from ..storage.questions import BankStore, QuestionStore
from ..utils.errors import DataError, LLMError
from ..utils.matching import normalize_question, question_similarity, render_answer_template
from ..utils.text import collapse_whitespace
from .updateData import refresh_statuses

log = logging.getLogger(__name__)

_TRUE_ANSWERS = {"true", "yes", "y", "1", "authorized"}
_FALSE_ANSWERS = {"false", "no", "n", "0", "not authorized"}


def normalize_boolean_answer(value: str) -> str | None:
    """Map common yes/no spellings to the canonical ``true``/``false``."""
    cleaned = collapse_whitespace(value).strip(" .!").casefold()
    if cleaned in _TRUE_ANSWERS:
        return "true"
    if cleaned in _FALSE_ANSWERS:
        return "false"
    return None


def normalize_choice_answer(value: str, options: list[str]) -> str | None:
    """Return the exact option text matching ``value``, if any."""
    cleaned = normalize_question(value)
    for option in options:
        if normalize_question(option) == cleaned:
            return option
    return None


def best_bank_match(
    question: str,
    kind: AnswerKind,
    answers: list[BankAnswer],
    *,
    job_type: str = "",
    job_field: str = "",
    threshold: float = 0.82,
) -> tuple[BankAnswer, float] | None:
    """Find the most similar approved bank answer compatible with ``kind``."""
    best: tuple[BankAnswer, float] | None = None
    for answer in answers:
        if answer.status != BankStatus.APPROVED or not answer.answer.strip():
            continue
        if not _compatible_kind(kind, answer.kind):
            continue
        score = question_similarity(question, answer.question or answer.normalized)
        if job_type and answer.job_type and answer.job_type.casefold() == job_type.casefold():
            score = min(1.0, score + 0.03)
        if job_field and answer.job_field and answer.job_field.casefold() == job_field.casefold():
            score = min(1.0, score + 0.03)
        if score >= threshold and (best is None or score > best[1]):
            best = (answer, score)
    return best


def _compatible_kind(question_kind: AnswerKind, bank_kind: AnswerKind) -> bool:
    if question_kind == AnswerKind.FILE:
        return False
    if question_kind == AnswerKind.BOOLEAN:
        return bank_kind == AnswerKind.BOOLEAN
    if question_kind == AnswerKind.MULTIPLE_CHOICE:
        return bank_kind in {AnswerKind.MULTIPLE_CHOICE, AnswerKind.FREE_TEXT}
    return bank_kind != AnswerKind.FILE


def extract_question_fields(
    html: str,
    *,
    job: Job,
    description: str = "",
    config: Config | None = None,
    provider: LLMProvider | None = None,
    use_ai: bool = False,
) -> list[FormField]:
    """Extract fields from HTML and optionally let an LLM clean them up."""
    fields = extract_fields_from_html(html)
    if not use_ai or not fields:
        return fields
    if config is None:
        raise DataError("LLM refinement requires configuration")
    active_provider = provider or build_provider(config)
    payload = [
        {
            "field_ref": field.field_ref,
            "label": field.label,
            "kind": field.kind.value,
            "options": field.options,
        }
        for field in fields
    ]
    system, prompt = build_extraction_prompt(job=_job_payload(job, description), fields=payload)
    try:
        response = active_provider.complete(
            system,
            prompt,
            temperature=0.0,
            max_tokens=1500,
        )
        refined = parse_json_array(response)
    except (LLMError, ValueError) as exc:
        log.warning("LLM question refinement failed; using heuristics: %s", exc)
        return fields
    if not refined:
        return []
    by_ref = {field.field_ref: field for field in fields}
    result: list[FormField] = []
    for item in refined:
        ref = str(item.get("field_ref", "")).strip()
        original = by_ref.get(ref)
        if original is None:
            continue
        label = collapse_whitespace(str(item.get("question", ""))) or original.label
        try:
            kind = parse_answer_kind(str(item.get("kind", original.kind.value)))
        except ValueError:
            kind = original.kind
        if original.looks_like_resume:
            kind = AnswerKind.FILE
        options = item.get("options")
        clean_options = (
            [str(option) for option in options if str(option).strip()]
            if isinstance(options, list)
            else original.options
        )
        result.append(
            replace(
                original,
                label=label,
                kind=kind,
                options=clean_options,
            )
        )
    return result or fields


def scan_questions(
    config: Config,
    job_id: str,
    html: str,
    *,
    source: str = "html",
    use_ai: bool = False,
    provider: LLMProvider | None = None,
) -> list[Question]:
    """Extract form questions for a job, reusing approved answers where safe."""
    job_store = JobStore.from_config(config)
    question_store = QuestionStore.from_config(config)
    bank_store = BankStore.from_config(config)
    jobs = job_store.load()
    job = job_store.require(job_id, jobs)
    description = job_store.read_description(job)
    fields = extract_question_fields(
        html,
        job=job,
        description=description,
        config=config,
        provider=provider,
        use_ai=use_ai,
    )
    if not fields:
        return []

    active_provider = provider
    if use_ai and active_provider is None:
        try:
            active_provider = build_provider(config)
        except LLMError:
            active_provider = None
    resume_text = _load_resume(config)
    questions = question_store.load()
    bank = bank_store.load()
    existing_by_ref = {
        question.field_ref: question for question in questions if question.job_id == job_id
    }
    existing_by_id = {question.question_id: question for question in questions}
    now = isoformat()
    bank_changed = False

    for field in fields:
        normalized = normalize_question(field.label)
        if not normalized:
            continue
        template = Question.create(
            job_id=job_id,
            question=field.label,
            normalized=normalized,
            field_ref=field.field_ref,
            kind=field.kind,
            options=field.options,
            source=source,
            now=now,
        )
        existing = existing_by_ref.get(field.field_ref) or existing_by_id.get(template.question_id)
        if existing is not None:
            question = existing
            question.question = field.label
            question.normalized = normalized
            question.kind = field.kind
            question.options = field.options
            question.field_ref = field.field_ref
            question.source = source
            question.updated_at = now
        else:
            question = template
            questions.append(question)
            existing_by_id[question.question_id] = question
            existing_by_ref[question.field_ref] = question

        if question.kind == AnswerKind.FILE:
            _apply_file_answer(config, question)
            continue
        if question.status != QuestionStatus.UNANSWERED:
            continue

        match = best_bank_match(
            question.question,
            question.kind,
            bank,
            job_type=job.job_type,
            job_field=job.field,
            threshold=config.matching.similarity_threshold,
        )
        if match is None:
            continue
        bank_answer, score = match
        question.answer_id = bank_answer.answer_id
        question.confidence = f"{score:.3f}"
        reference = render_answer_template(
            bank_answer.answer,
            company=job.company,
            role=job.title,
            name=config.general.name,
        )
        question.answer = reference
        question.status = QuestionStatus.REUSED
        if use_ai and active_provider is not None and config.llm.adapt_reused_answers:
            adapted = _adapt_answer(
                config,
                active_provider,
                job,
                description,
                question,
                reference,
                resume_text,
            )
            if adapted:
                question.answer = adapted
                question.status = QuestionStatus.NEEDS_REVIEW
        bank_answer.times_used += 1
        bank_answer.last_used = now
        bank_changed = True

    question_store.save_all(questions)
    if bank_changed:
        bank_store.save_all(bank)
    refresh_statuses(config, [job_id])
    return [question for question in questions if question.job_id == job_id]


def draft_answers(
    config: Config,
    job_id: str,
    *,
    provider: LLMProvider | None = None,
    include_existing: bool = False,
) -> list[Question]:
    """Generate drafts for unanswered questions. Drafts still need approval."""
    active_provider = provider or build_provider(config)
    job_store = JobStore.from_config(config)
    question_store = QuestionStore.from_config(config)
    bank_store = BankStore.from_config(config)
    jobs = job_store.load()
    job = job_store.require(job_id, jobs)
    description = job_store.read_description(job)
    questions = question_store.load()
    bank = bank_store.load()
    bank_by_id = {answer.answer_id: answer for answer in bank}
    resume_text = _load_resume(config)
    targets = [
        question
        for question in questions
        if question.job_id == job_id
        and question.kind != AnswerKind.FILE
        and (
            include_existing
            or question.status in {QuestionStatus.UNANSWERED, QuestionStatus.NEEDS_REVIEW}
        )
    ]
    if not targets:
        return [question for question in questions if question.job_id == job_id]

    for question in targets:
        reference = ""
        if question.answer_id and question.answer_id in bank_by_id:
            reference = render_answer_template(
                bank_by_id[question.answer_id].answer,
                company=job.company,
                role=job.title,
                name=config.general.name,
            )
        system, prompt = build_answer_prompt(
            profile=_profile_payload(config),
            job=_job_payload(job, description),
            question=question.question,
            kind=question.kind.value,
            options=question.options,
            reference_answer=reference,
            resume=resume_text,
            max_resume_chars=config.llm.max_resume_chars,
        )
        try:
            answer = active_provider.complete(
                system,
                prompt,
                temperature=config.llm.temperature,
                max_tokens=300 if question.kind == AnswerKind.BOOLEAN else 1200,
            )
        except LLMError as exc:
            log.warning("Draft failed for %s: %s", question.question_id, exc)
            continue
        answer = answer.strip()
        question.updated_at = isoformat()
        if not answer or is_unknown(answer):
            question.status = QuestionStatus.UNANSWERED
            question.notes = _merge_note(question.notes, "AI could not answer from profile")
            continue
        question.answer, note = _postprocess_answer(answer, question.kind, question.options)
        question.notes = _merge_note(question.notes, note)
        question.status = QuestionStatus.NEEDS_REVIEW
        question.source = question.source or "ai"
    question_store.save_all(questions)
    refresh_statuses(config, [job_id])
    return [question for question in questions if question.job_id == job_id]


def set_answer(
    config: Config,
    question_id: str,
    answer: str,
    *,
    approve: bool = True,
    notes: str = "",
) -> tuple[Question, BankAnswer | None]:
    """Set/approve an answer and update the reusable bank."""
    job_store = JobStore.from_config(config)
    question_store = QuestionStore.from_config(config)
    bank_store = BankStore.from_config(config)
    questions = question_store.load()
    question = question_store.get(question_id, questions)
    if question is None:
        raise DataError(f"Unknown question id: {question_id}")
    job = job_store.get(question.job_id)
    if job is None:
        raise DataError(f"Question {question_id} points at unknown job {question.job_id}")

    cleaned = answer.strip()
    if question.kind == AnswerKind.BOOLEAN:
        normalized = normalize_boolean_answer(cleaned)
        if normalized is None:
            raise DataError("Boolean answers must be true/false (or yes/no).")
        cleaned = normalized
    elif question.kind == AnswerKind.MULTIPLE_CHOICE:
        choice = normalize_choice_answer(cleaned, question.options)
        if choice is None:
            raise DataError(
                "Answer must match one of: " + ", ".join(question.options or ["(no options)"])
            )
        cleaned = choice
    if not cleaned:
        raise DataError("Answer cannot be empty.")

    now = isoformat()
    question.answer = cleaned
    question.updated_at = now
    question.status = QuestionStatus.APPROVED if approve else QuestionStatus.NEEDS_REVIEW
    if notes:
        question.notes = _merge_note(question.notes, notes)
    bank_answer: BankAnswer | None = None
    if approve:
        bank = bank_store.load()
        bank_answer = bank_store.get(question.answer_id, bank) if question.answer_id else None
        if bank_answer is None:
            bank_answer = bank_store.find_exact(question.normalized, bank)
        if bank_answer is None:
            bank_answer = BankAnswer.create(
                question=question.question,
                normalized=question.normalized,
                answer=cleaned,
                kind=question.kind,
                status=BankStatus.APPROVED,
                category=job.field,
                job_type=job.job_type,
                job_field=job.field,
                now=now,
            )
            bank.append(bank_answer)
        else:
            bank_answer.answer = cleaned
            bank_answer.kind = question.kind
            bank_answer.status = BankStatus.APPROVED
            bank_answer.updated_at = now
            if not bank_answer.question:
                bank_answer.question = question.question
        question.answer_id = bank_answer.answer_id
        bank_store.save_all(bank)
    question_store.save_all(questions)
    refresh_statuses(config, [question.job_id])
    return question, bank_answer


def approve_question(config: Config, question_id: str) -> Question:
    question_store = QuestionStore.from_config(config)
    question = question_store.get(question_id)
    if question is None:
        raise DataError(f"Unknown question id: {question_id}")
    if not question.answer.strip():
        raise DataError("Question has no answer to approve.")
    updated, _ = set_answer(config, question_id, question.answer, approve=True)
    return updated


def skip_question(config: Config, question_id: str) -> Question:
    question_store = QuestionStore.from_config(config)
    questions = question_store.load()
    question = question_store.get(question_id, questions)
    if question is None:
        raise DataError(f"Unknown question id: {question_id}")
    question.status = QuestionStatus.SKIPPED
    question.updated_at = isoformat()
    question_store.save_all(questions)
    refresh_statuses(config, [question.job_id])
    return question


def _adapt_answer(
    config: Config,
    provider: LLMProvider,
    job: Job,
    description: str,
    question: Question,
    reference: str,
    resume_text: str,
) -> str | None:
    system, prompt = build_answer_prompt(
        profile=_profile_payload(config),
        job=_job_payload(job, description),
        question=question.question,
        kind=question.kind.value,
        options=question.options,
        reference_answer=reference,
        resume=resume_text,
        max_resume_chars=config.llm.max_resume_chars,
    )
    try:
        answer = provider.complete(
            system,
            prompt,
            temperature=config.llm.temperature,
            max_tokens=800,
        ).strip()
    except LLMError as exc:
        log.warning("Answer adaptation failed; keeping approved text: %s", exc)
        return None
    if not answer or is_unknown(answer):
        return None
    processed, note = _postprocess_answer(answer, question.kind, question.options)
    if note:
        question.notes = _merge_note(question.notes, note)
    return processed


def _apply_file_answer(config: Config, question: Question) -> None:
    path = config.resume_path
    if path.is_file():
        question.answer = str(path)
        question.status = QuestionStatus.APPROVED
        question.updated_at = isoformat()
    else:
        question.status = QuestionStatus.UNANSWERED
        question.notes = _merge_note(
            question.notes, f"Resume not found at {path}; upload it before autofilling"
        )


def _postprocess_answer(answer: str, kind: AnswerKind, options: list[str]) -> tuple[str, str]:
    if kind == AnswerKind.BOOLEAN:
        normalized = normalize_boolean_answer(answer)
        if normalized is None:
            return answer, "AI returned a non-boolean answer; expected true/false"
        return normalized, ""
    if kind == AnswerKind.MULTIPLE_CHOICE:
        choice = normalize_choice_answer(answer, options)
        if choice is None:
            return answer, "AI answer did not match the form options"
        return choice, ""
    return answer, ""


def _profile_payload(config: Config) -> Mapping[str, object]:
    return {
        "name": config.general.name,
        "email": config.general.email,
        "phone": config.general.phone,
        "address": config.general.address,
        "current_employment": config.general.current_employment,
        "links": config.general.links,
    }


def _job_payload(job: Job, description: str) -> Mapping[str, object]:
    return {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "job_type": job.job_type,
        "field": job.field,
        "tags": job.tags,
        "description": description,
    }


def _load_resume(config: Config) -> str:
    try:
        from ..services.resume import load_resume

        return load_resume(config)
    except Exception as exc:  # noqa: BLE001 - resume is optional for generic answers
        log.warning("Could not load resume: %s", exc)
        return ""


def _merge_note(existing: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return existing
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}; {addition}"


__all__ = [
    "approve_question",
    "best_bank_match",
    "draft_answers",
    "extract_question_fields",
    "normalize_boolean_answer",
    "normalize_choice_answer",
    "scan_questions",
    "set_answer",
    "skip_question",
]

"""Application packets, submission tracking, and autofill orchestration."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ..config import Config
from ..models import (
    Application,
    ApplicationStatus,
    Job,
    JobStatus,
    Question,
    QuestionStatus,
    isoformat,
)
from ..storage.applications import ApplicationStore
from ..storage.jobs import JobStore
from ..storage.questions import QuestionStore
from ..utils.errors import DataError
from ..utils.text import slugify

_TERMINAL_QUESTIONS = {
    QuestionStatus.APPROVED,
    QuestionStatus.REUSED,
    QuestionStatus.SKIPPED,
}


def generate_packet(
    config: Config,
    job_id: str,
    *,
    out_dir: Path | None = None,
) -> Path:
    """Write a human-readable application packet and mark the job ready."""
    job_store = JobStore.from_config(config)
    question_store = QuestionStore.from_config(config)
    jobs = job_store.load()
    job = job_store.require(job_id, jobs)
    questions = question_store.for_job(job_id)
    description = job_store.read_description(job)
    out_dir = out_dir or config.applications_dir
    folder = out_dir / f"{slugify(job.company)}-{slugify(job.title)}-{job.job_id}"
    path = folder / "application.md"
    markdown = render_packet(config, job, description, questions)
    _write_text(path, markdown)

    job.packet_path = _reference(path, config.root)
    if job.status not in {JobStatus.APPLIED, JobStatus.SKIPPED, JobStatus.FILTERED_OUT}:
        if all(question.status in _TERMINAL_QUESTIONS for question in questions):
            job.status = JobStatus.PACKET_READY
    job_store.save_all(jobs)
    return path


def render_packet(
    config: Config,
    job: Job,
    description: str,
    questions: list[Question],
) -> str:
    """Render the editable Markdown packet for one job."""
    lines = [
        f"# {job.title} — {job.company}",
        "",
        "> Review every answer below before submitting. This packet was generated",
        "> by jobscraper, which never submits an application automatically.",
        "",
        "## Job",
        "",
        f"- **Company:** {job.company}",
        f"- **Title:** {job.title}",
        f"- **Location:** {job.location or '—'}",
        f"- **Type:** {job.job_type or '—'}",
        f"- **Field:** {job.field or '—'}",
        f"- **Source:** {job.source or '—'}",
        f"- **Status:** {job.status.value}",
        f"- **Posting:** {job.url or '—'}",
        f"- **Apply:** {job.apply_url or '—'}",
        f"- **Tags:** {', '.join(job.tags) or '—'}",
        f"- **Resume:** {config.resume_path}",
        "",
    ]
    if job.notes.strip():
        lines += ["## Notes", "", job.notes.strip(), ""]
    lines += [
        "## Questions and answers",
        "",
    ]
    if not questions:
        lines += [
            "_No application questions have been scanned yet. Use_",
            f"_`uv run jobscraper questions scan {job.job_id} --url <form-url>`._",
            "",
        ]
    else:
        for index, question in enumerate(questions, start=1):
            lines += [
                f"### {index}. {question.question}",
                "",
                f"- **Question ID:** `{question.question_id}`",
                f"- **Kind:** {question.kind.value}",
                f"- **Status:** {question.status.value}",
            ]
            if question.options:
                lines.append(f"- **Options:** {' | '.join(question.options)}")
            if question.answer_id:
                lines.append(f"- **Bank answer:** `{question.answer_id}`")
            if question.confidence:
                lines.append(f"- **Match confidence:** {question.confidence}")
            if question.notes.strip():
                lines.append(f"- **Notes:** {question.notes.strip()}")
            lines += ["", "**Answer:**", ""]
            answer = question.answer.strip() or "_Unanswered_"
            lines += [f"> {line}" if line else ">" for line in answer.splitlines()]
            lines.append("")
    lines += ["## Submission checklist", ""]
    lines += [
        "- [ ] Review the job posting and confirm it is a good fit.",
        "- [ ] Resolve any questions marked `unanswered` or `needs_review`.",
        "- [ ] Attach the resume shown above.",
        "- [ ] Fill the form with `uv run jobscraper autofill "
        f"{job.job_id} --url <form-url> --fill`.",
        "- [ ] Review the browser form and click submit yourself.",
        f"- [ ] Record the submission: `uv run jobscraper track {job.job_id}`.",
        "",
    ]
    if description:
        lines += ["## Job description", "", description.strip(), ""]
    return "\n".join(lines)


def track_application(
    config: Config,
    job_id: str,
    *,
    status: ApplicationStatus = ApplicationStatus.APPLIED,
    notes: str = "",
    force: bool = False,
) -> Application:
    """Record a submission, guarding against duplicates in the same season."""
    job_store = JobStore.from_config(config)
    application_store = ApplicationStore.from_config(config)
    jobs = job_store.load()
    job = job_store.require(job_id, jobs)
    applications = application_store.load()
    existing = next(
        (
            application
            for application in applications
            if application.job_id == job_id and application.season == config.season
        ),
        None,
    )
    if existing is None and config.application.duplicate_guard and not force:
        duplicate = application_store.find_duplicate(
            company=job.company,
            title=job.title,
            season=config.season,
            applications=applications,
        )
        if duplicate is not None:
            raise DataError(
                "A matching company/title was already recorded for season "
                f"{config.season}: {duplicate.application_id} ({duplicate.applied_at}). "
                "Use --force only if this is genuinely a different opening."
            )
    now = isoformat()
    if existing is not None:
        application = existing
        application.status = status
        application.updated_at = now
        if notes:
            application.notes = _append_note(application.notes, notes)
        if not application.packet_path:
            application.packet_path = job.packet_path
    else:
        application = Application.create(
            job=job,
            season=config.season,
            resume=str(config.resume_path),
            packet_path=job.packet_path,
            notes=notes,
            now=now,
        )
        application.status = status
        applications.append(application)
    job.status = JobStatus.APPLIED
    job.applied_at = job.applied_at or now
    if notes:
        job.notes = _append_note(job.notes, notes)
    application_store.save_all(applications)
    job_store.save_all(jobs)
    return application


def update_application(
    config: Config,
    application_id: str,
    *,
    status: ApplicationStatus | None = None,
    notes: str = "",
) -> Application:
    store = ApplicationStore.from_config(config)
    applications = store.load()
    application = store.get(application_id, applications)
    if application is None:
        raise DataError(f"Unknown application id: {application_id}")
    if status is not None:
        application.status = status
    if notes:
        application.notes = _append_note(application.notes, notes)
    application.updated_at = isoformat()
    store.save_all(applications)
    return application


def _append_note(existing: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return existing
    return f"{existing}\n{addition}".strip() if existing else addition


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, path)
    except OSError as exc:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise DataError(f"Could not write packet {path}: {exc}") from exc


def _reference(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path.resolve())


__all__ = [
    "generate_packet",
    "render_packet",
    "track_application",
    "update_application",
]

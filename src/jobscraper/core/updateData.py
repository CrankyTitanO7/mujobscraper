"""Keep job statuses consistent with questions, packets, and applications."""

from __future__ import annotations

from ..config import Config
from ..models import Job, JobStatus, QuestionStatus
from ..storage.applications import ApplicationStore
from ..storage.jobs import JobStore
from ..storage.questions import QuestionStore

_TERMINAL_QUESTION_STATES = {
    QuestionStatus.APPROVED,
    QuestionStatus.REUSED,
    QuestionStatus.SKIPPED,
}


def refresh_statuses(config: Config, job_ids: list[str] | None = None) -> list[Job]:
    """Recalculate job statuses from the editable tables.

    Collected jobs remain ``new``/``filtered_out`` until application questions
    exist. Once all questions are answered the job becomes ``answered``; an
    application row always wins and marks the job ``applied``.
    """
    job_store = JobStore.from_config(config)
    question_store = QuestionStore.from_config(config)
    application_store = ApplicationStore.from_config(config)
    jobs = job_store.load()
    questions = question_store.load()
    applications = application_store.load()
    selected = set(job_ids) if job_ids else None
    changed = False

    applied_job_ids = {application.job_id for application in applications}
    questions_by_job: dict[str, list] = {}
    for question in questions:
        questions_by_job.setdefault(question.job_id, []).append(question)

    for job in jobs:
        if selected is not None and job.job_id not in selected:
            continue
        before = job.status
        if job.job_id in applied_job_ids:
            job.status = JobStatus.APPLIED
        elif job.status in {JobStatus.SKIPPED, JobStatus.FILTERED_OUT}:
            pass
        elif questions_by_job.get(job.job_id):
            job_questions = questions_by_job[job.job_id]
            if all(question.status in _TERMINAL_QUESTION_STATES for question in job_questions):
                job.status = JobStatus.ANSWERED
            else:
                job.status = JobStatus.ANSWERING
        elif job.status in {JobStatus.ANSWERING, JobStatus.ANSWERED, JobStatus.PACKET_READY}:
            job.status = JobStatus.NEW
        if job.status != before:
            changed = True
    if changed:
        job_store.save_all(jobs)
    return [job for job in jobs if selected is None or job.job_id in selected]


__all__ = ["refresh_statuses"]

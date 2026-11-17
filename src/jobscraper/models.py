"""Domain records and shared enums.

Records are plain dataclasses (not ORM objects) on purpose: every table can be
opened, edited, and re-read by a human between commands.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime
from enum import StrEnum


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def isoformat(value: datetime | None = None) -> str:
    """Serialize a timestamp for CSV storage (seconds precision)."""
    value = value or utcnow()
    return value.replace(microsecond=0).isoformat()


def parse_datetime(value: str) -> datetime | None:
    """Best-effort parse of ISO-8601 timestamps found in feeds and tables."""
    if not value or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def stable_id(prefix: str, *parts: str) -> str:
    """Build a deterministic, short identifier from arbitrary text parts."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def normalize_key(*parts: str) -> str:
    """Normalize text for deduplication keys."""
    text = " ".join(parts).casefold()
    text = re.sub(r"[^a-z0-9+#.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class JobStatus(StrEnum):
    """Lifecycle of a discovered job."""

    NEW = "new"
    FILTERED_OUT = "filtered_out"
    ANSWERING = "answering"
    ANSWERED = "answered"
    PACKET_READY = "packet_ready"
    APPLIED = "applied"
    SKIPPED = "skipped"


class QuestionStatus(StrEnum):
    """Lifecycle of a question tied to one job."""

    UNANSWERED = "unanswered"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REUSED = "reused"
    SKIPPED = "skipped"


class AnswerKind(StrEnum):
    """Input shape expected by a question."""

    FREE_TEXT = "free_text"
    BOOLEAN = "boolean"
    MULTIPLE_CHOICE = "multiple_choice"
    FILE = "file"


class BankStatus(StrEnum):
    """Lifecycle of a reusable answer in the answer bank."""

    APPROVED = "approved"
    DRAFT = "draft"
    ARCHIVED = "archived"


class ApplicationStatus(StrEnum):
    """Lifecycle of an application after it is submitted."""

    APPLIED = "applied"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    OFFER = "offer"
    WITHDRAWN = "withdrawn"


JOB_STATUS_ALIASES: dict[str, JobStatus] = {
    "not started": JobStatus.NEW,
    "not_started": JobStatus.NEW,
    "filtered": JobStatus.FILTERED_OUT,
    "filtered out": JobStatus.FILTERED_OUT,
    "packet": JobStatus.PACKET_READY,
    "packet ready": JobStatus.PACKET_READY,
    "submitted": JobStatus.APPLIED,
}


def parse_job_status(value: str) -> JobStatus:
    raw = (value or "").strip().casefold().replace("-", "_")
    if raw in JOB_STATUS_ALIASES:
        return JOB_STATUS_ALIASES[raw]
    return JobStatus(raw)


def parse_question_status(value: str) -> QuestionStatus:
    raw = (value or "").strip().casefold().replace("-", "_")
    aliases = {
        "draft": QuestionStatus.NEEDS_REVIEW,
        "answered": QuestionStatus.APPROVED,
        "pending": QuestionStatus.UNANSWERED,
    }
    return aliases.get(raw, QuestionStatus(raw))


def parse_answer_kind(value: str) -> AnswerKind:
    raw = (value or "").strip().casefold().replace("-", "_")
    aliases = {
        "text": AnswerKind.FREE_TEXT,
        "bool": AnswerKind.BOOLEAN,
        "yes_no": AnswerKind.BOOLEAN,
        "choice": AnswerKind.MULTIPLE_CHOICE,
        "select": AnswerKind.MULTIPLE_CHOICE,
        "upload": AnswerKind.FILE,
    }
    return aliases.get(raw, AnswerKind(raw))


def parse_bank_status(value: str) -> BankStatus:
    raw = (value or "").strip().casefold().replace("-", "_")
    return BankStatus(raw)


def parse_application_status(value: str) -> ApplicationStatus:
    raw = (value or "").strip().casefold().replace("-", "_")
    return ApplicationStatus(raw)


@dataclass(slots=True)
class JobPosting:
    """A normalized job returned by a source adapter."""

    title: str
    company: str
    source: str
    source_id: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    apply_url: str = ""
    tags: list[str] = dc_field(default_factory=list)
    job_type: str = ""
    field: str = ""
    posted_at: str = ""

    @property
    def job_id(self) -> str:
        identity = (
            self.source_id
            or self.url
            or self.apply_url
            or f"{normalize_key(self.company, self.title, self.location)}"
        )
        return stable_id("job", self.source.casefold(), identity)

    @property
    def application_key(self) -> str:
        """Key used to prevent the same role being applied to twice."""
        return normalize_key(self.company, self.title)


@dataclass(slots=True)
class Job:
    """A job row from ``jobStatusTable``."""

    job_id: str
    status: JobStatus
    title: str
    company: str
    location: str = ""
    job_type: str = ""
    field: str = ""
    source: str = ""
    source_id: str = ""
    url: str = ""
    apply_url: str = ""
    tags: list[str] = dc_field(default_factory=list)
    include_matches: list[str] = dc_field(default_factory=list)
    exclude_matches: list[str] = dc_field(default_factory=list)
    posted_at: str = ""
    first_seen: str = ""
    last_seen: str = ""
    applied_at: str = ""
    notes: str = ""
    description_path: str = ""
    packet_path: str = ""
    extra: dict[str, str] = dc_field(default_factory=dict, repr=False)

    @property
    def application_key(self) -> str:
        return normalize_key(self.company, self.title)

    @classmethod
    def from_posting(
        cls,
        posting: JobPosting,
        *,
        status: JobStatus = JobStatus.NEW,
        include_matches: list[str] | None = None,
        exclude_matches: list[str] | None = None,
        description_path: str = "",
        now: str = "",
    ) -> Job:
        timestamp = now or isoformat()
        return cls(
            job_id=posting.job_id,
            status=status,
            title=posting.title,
            company=posting.company,
            location=posting.location,
            job_type=posting.job_type,
            field=posting.field,
            source=posting.source,
            source_id=posting.source_id,
            url=posting.url,
            apply_url=posting.apply_url,
            tags=list(posting.tags),
            include_matches=include_matches or [],
            exclude_matches=exclude_matches or [],
            posted_at=posting.posted_at,
            first_seen=timestamp,
            last_seen=timestamp,
            description_path=description_path,
        )


@dataclass(slots=True)
class Question:
    """A job-specific form question from ``questionsTable``."""

    question_id: str
    job_id: str
    question: str
    normalized: str = ""
    field_ref: str = ""
    kind: AnswerKind = AnswerKind.FREE_TEXT
    options: list[str] = dc_field(default_factory=list)
    answer: str = ""
    status: QuestionStatus = QuestionStatus.UNANSWERED
    answer_id: str = ""
    confidence: str = ""
    source: str = ""
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""
    extra: dict[str, str] = dc_field(default_factory=dict, repr=False)

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        question: str,
        normalized: str,
        field_ref: str = "",
        kind: AnswerKind = AnswerKind.FREE_TEXT,
        options: list[str] | None = None,
        source: str = "",
        now: str = "",
    ) -> Question:
        timestamp = now or isoformat()
        return cls(
            question_id=stable_id("q", job_id, field_ref or normalized, normalized),
            job_id=job_id,
            question=question.strip(),
            normalized=normalized,
            field_ref=field_ref,
            kind=kind,
            options=options or [],
            source=source,
            created_at=timestamp,
            updated_at=timestamp,
        )


@dataclass(slots=True)
class BankAnswer:
    """A reusable answer from ``questionBankTable``."""

    answer_id: str
    question: str
    normalized: str
    answer: str
    kind: AnswerKind = AnswerKind.FREE_TEXT
    status: BankStatus = BankStatus.APPROVED
    category: str = ""
    job_type: str = ""
    job_field: str = ""
    times_used: int = 0
    last_used: str = ""
    created_at: str = ""
    updated_at: str = ""
    notes: str = ""
    extra: dict[str, str] = dc_field(default_factory=dict, repr=False)

    @classmethod
    def create(
        cls,
        *,
        question: str,
        normalized: str,
        answer: str,
        kind: AnswerKind = AnswerKind.FREE_TEXT,
        status: BankStatus = BankStatus.APPROVED,
        category: str = "",
        job_type: str = "",
        job_field: str = "",
        notes: str = "",
        now: str = "",
    ) -> BankAnswer:
        timestamp = now or isoformat()
        return cls(
            answer_id=stable_id("a", normalized, kind.value),
            question=question.strip(),
            normalized=normalized,
            answer=answer.strip(),
            kind=kind,
            status=status,
            category=category,
            job_type=job_type,
            job_field=job_field,
            notes=notes,
            created_at=timestamp,
            updated_at=timestamp,
        )


@dataclass(slots=True)
class Application:
    """A submitted application row from ``jobAppliedTable``."""

    application_id: str
    job_id: str
    company: str
    title: str
    season: str
    status: ApplicationStatus = ApplicationStatus.APPLIED
    applied_at: str = ""
    updated_at: str = ""
    resume: str = ""
    packet_path: str = ""
    notes: str = ""
    extra: dict[str, str] = dc_field(default_factory=dict, repr=False)

    @classmethod
    def create(
        cls,
        *,
        job: Job,
        season: str,
        resume: str = "",
        packet_path: str = "",
        notes: str = "",
        now: str = "",
    ) -> Application:
        timestamp = now or isoformat()
        return cls(
            application_id=stable_id(
                "app", job.job_id, season, timestamp.replace(":", "").replace("-", "")
            ),
            job_id=job.job_id,
            company=job.company,
            title=job.title,
            season=season,
            applied_at=timestamp,
            updated_at=timestamp,
            resume=resume,
            packet_path=packet_path,
            notes=notes,
        )

    @property
    def application_key(self) -> str:
        return normalize_key(self.company, self.title)

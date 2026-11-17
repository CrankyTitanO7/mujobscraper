"""CSV repositories for job-specific questions and reusable answers."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..models import (
    BankAnswer,
    BankStatus,
    Question,
    isoformat,
    parse_answer_kind,
    parse_bank_status,
    parse_question_status,
)
from ..utils.errors import DataError
from .csv_store import CsvTable, join_list, split_list

QUESTION_FIELDS = [
    "question_id",
    "job_id",
    "field_ref",
    "question",
    "normalized",
    "kind",
    "options",
    "answer",
    "status",
    "answer_id",
    "confidence",
    "source",
    "created_at",
    "updated_at",
    "notes",
]

BANK_FIELDS = [
    "answer_id",
    "question",
    "normalized",
    "kind",
    "answer",
    "status",
    "category",
    "job_type",
    "job_field",
    "times_used",
    "last_used",
    "created_at",
    "updated_at",
    "notes",
]


class QuestionStore:
    """Read/write questions tied to jobs."""

    def __init__(self, path: Path) -> None:
        self.table = CsvTable(path, QUESTION_FIELDS)

    @classmethod
    def from_config(cls, config: Config) -> QuestionStore:
        return cls(config.resolve_path(config.paths.questions_table))

    def load(self) -> list[Question]:
        return [self._from_row(row) for row in self.table.read()]

    def save_all(self, questions: list[Question]) -> None:
        self.table.write([self._to_row(question) for question in questions])

    def ensure(self) -> None:
        self.table.ensure()

    def for_job(self, job_id: str, questions: list[Question] | None = None) -> list[Question]:
        source = questions if questions is not None else self.load()
        return [question for question in source if question.job_id == job_id]

    def get(self, question_id: str, questions: list[Question] | None = None) -> Question | None:
        source = questions if questions is not None else self.load()
        return next((question for question in source if question.question_id == question_id), None)

    def _from_row(self, row: dict[str, str]) -> Question:
        if not row.get("question_id", "").strip() or not row.get("job_id", "").strip():
            raise DataError(f"{self.table.path}: question rows need question_id and job_id")
        try:
            kind = parse_answer_kind(row.get("kind", ""))
            status = parse_question_status(row.get("status", ""))
        except ValueError as exc:
            raise DataError(
                f"{self.table.path}: invalid kind/status in {row.get('question_id')}"
            ) from exc
        extra = {key: value for key, value in row.items() if key not in QUESTION_FIELDS}
        return Question(
            question_id=row["question_id"].strip(),
            job_id=row["job_id"].strip(),
            question=row.get("question", "").strip(),
            normalized=row.get("normalized", "").strip(),
            field_ref=row.get("field_ref", "").strip(),
            kind=kind,
            options=split_list(row.get("options", "")),
            answer=row.get("answer", ""),
            status=status,
            answer_id=row.get("answer_id", "").strip(),
            confidence=row.get("confidence", "").strip(),
            source=row.get("source", "").strip(),
            created_at=row.get("created_at", "").strip(),
            updated_at=row.get("updated_at", "").strip(),
            notes=row.get("notes", ""),
            extra=extra,
        )

    def _to_row(self, question: Question) -> dict[str, str]:
        row = {
            "question_id": question.question_id,
            "job_id": question.job_id,
            "field_ref": question.field_ref,
            "question": question.question,
            "normalized": question.normalized,
            "kind": question.kind.value,
            "options": join_list(question.options),
            "answer": question.answer,
            "status": question.status.value,
            "answer_id": question.answer_id,
            "confidence": question.confidence,
            "source": question.source,
            "created_at": question.created_at,
            "updated_at": question.updated_at or isoformat(),
            "notes": question.notes,
        }
        row.update(question.extra)
        return row


class BankStore:
    """Read/write the reusable, human-editable answer bank."""

    def __init__(self, path: Path) -> None:
        self.table = CsvTable(path, BANK_FIELDS)

    @classmethod
    def from_config(cls, config: Config) -> BankStore:
        return cls(config.resolve_path(config.paths.question_bank_table))

    def load(self) -> list[BankAnswer]:
        return [self._from_row(row) for row in self.table.read()]

    def save_all(self, answers: list[BankAnswer]) -> None:
        self.table.write([self._to_row(answer) for answer in answers])

    def ensure(self) -> None:
        self.table.ensure()

    def approved(self, answers: list[BankAnswer] | None = None) -> list[BankAnswer]:
        source = answers if answers is not None else self.load()
        return [answer for answer in source if answer.status == BankStatus.APPROVED]

    def get(self, answer_id: str, answers: list[BankAnswer] | None = None) -> BankAnswer | None:
        source = answers if answers is not None else self.load()
        return next((answer for answer in source if answer.answer_id == answer_id), None)

    def find_exact(
        self, normalized: str, answers: list[BankAnswer] | None = None
    ) -> BankAnswer | None:
        source = answers if answers is not None else self.load()
        return next((answer for answer in source if answer.normalized == normalized), None)

    def _from_row(self, row: dict[str, str]) -> BankAnswer:
        if not row.get("answer_id", "").strip():
            raise DataError(f"{self.table.path}: bank rows need answer_id")
        try:
            kind = parse_answer_kind(row.get("kind", ""))
            status = parse_bank_status(row.get("status", ""))
        except ValueError as exc:
            raise DataError(
                f"{self.table.path}: invalid kind/status in {row.get('answer_id')}"
            ) from exc
        try:
            times_used = int(row.get("times_used", "0") or "0")
        except ValueError:
            times_used = 0
        extra = {key: value for key, value in row.items() if key not in BANK_FIELDS}
        return BankAnswer(
            answer_id=row["answer_id"].strip(),
            question=row.get("question", "").strip(),
            normalized=row.get("normalized", "").strip(),
            answer=row.get("answer", ""),
            kind=kind,
            status=status,
            category=row.get("category", "").strip(),
            job_type=row.get("job_type", "").strip(),
            job_field=row.get("job_field", "").strip(),
            times_used=times_used,
            last_used=row.get("last_used", "").strip(),
            created_at=row.get("created_at", "").strip(),
            updated_at=row.get("updated_at", "").strip(),
            notes=row.get("notes", ""),
            extra=extra,
        )

    def _to_row(self, answer: BankAnswer) -> dict[str, str]:
        row = {
            "answer_id": answer.answer_id,
            "question": answer.question,
            "normalized": answer.normalized,
            "kind": answer.kind.value,
            "answer": answer.answer,
            "status": answer.status.value,
            "category": answer.category,
            "job_type": answer.job_type,
            "job_field": answer.job_field,
            "times_used": str(answer.times_used),
            "last_used": answer.last_used,
            "created_at": answer.created_at,
            "updated_at": answer.updated_at or isoformat(),
            "notes": answer.notes,
        }
        row.update(answer.extra)
        return row

"""CSV repository for submitted applications."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..models import (
    Application,
    isoformat,
    normalize_key,
    parse_application_status,
)
from ..utils.errors import DataError
from .csv_store import CsvTable

APPLICATION_FIELDS = [
    "application_id",
    "job_id",
    "company",
    "title",
    "season",
    "status",
    "applied_at",
    "updated_at",
    "resume",
    "packet_path",
    "notes",
]


class ApplicationStore:
    """Read/write ``jobAppliedTable``."""

    def __init__(self, path: Path) -> None:
        self.table = CsvTable(path, APPLICATION_FIELDS)

    @classmethod
    def from_config(cls, config: Config) -> ApplicationStore:
        return cls(config.resolve_path(config.paths.job_applied_table))

    def load(self) -> list[Application]:
        return [self._from_row(row) for row in self.table.read()]

    def save_all(self, applications: list[Application]) -> None:
        self.table.write([self._to_row(application) for application in applications])

    def ensure(self) -> None:
        self.table.ensure()

    def get(
        self, application_id: str, applications: list[Application] | None = None
    ) -> Application | None:
        source = applications if applications is not None else self.load()
        return next(
            (application for application in source if application.application_id == application_id),
            None,
        )

    def for_job(
        self, job_id: str, applications: list[Application] | None = None
    ) -> list[Application]:
        source = applications if applications is not None else self.load()
        return [application for application in source if application.job_id == job_id]

    def find_duplicate(
        self,
        *,
        company: str,
        title: str,
        season: str,
        applications: list[Application] | None = None,
    ) -> Application | None:
        key = normalize_key(company, title)
        source = applications if applications is not None else self.load()
        return next(
            (
                application
                for application in source
                if application.application_key == key and application.season == season
            ),
            None,
        )

    def _from_row(self, row: dict[str, str]) -> Application:
        if not row.get("application_id", "").strip():
            raise DataError(f"{self.table.path}: application rows need application_id")
        try:
            status = parse_application_status(row.get("status", ""))
        except ValueError as exc:
            raise DataError(
                f"{self.table.path}: unknown application status {row.get('status')!r}"
            ) from exc
        extra = {key: value for key, value in row.items() if key not in APPLICATION_FIELDS}
        return Application(
            application_id=row["application_id"].strip(),
            job_id=row.get("job_id", "").strip(),
            company=row.get("company", "").strip(),
            title=row.get("title", "").strip(),
            season=row.get("season", "").strip(),
            status=status,
            applied_at=row.get("applied_at", "").strip(),
            updated_at=row.get("updated_at", "").strip(),
            resume=row.get("resume", "").strip(),
            packet_path=row.get("packet_path", "").strip(),
            notes=row.get("notes", ""),
            extra=extra,
        )

    def _to_row(self, application: Application) -> dict[str, str]:
        row = {
            "application_id": application.application_id,
            "job_id": application.job_id,
            "company": application.company,
            "title": application.title,
            "season": application.season,
            "status": application.status.value,
            "applied_at": application.applied_at,
            "updated_at": application.updated_at or isoformat(),
            "resume": application.resume,
            "packet_path": application.packet_path,
            "notes": application.notes,
        }
        row.update(application.extra)
        return row

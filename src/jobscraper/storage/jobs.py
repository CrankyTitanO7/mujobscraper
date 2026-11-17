"""CSV-backed repository for discovered jobs and their detail files."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ..config import Config
from ..models import Job, isoformat, parse_job_status
from ..utils.errors import DataError
from .csv_store import CsvTable, join_list, split_list

JOB_FIELDS = [
    "job_id",
    "status",
    "title",
    "company",
    "location",
    "job_type",
    "field",
    "source",
    "source_id",
    "url",
    "apply_url",
    "tags",
    "include_matches",
    "exclude_matches",
    "posted_at",
    "first_seen",
    "last_seen",
    "applied_at",
    "notes",
    "description_path",
    "packet_path",
]

_REQUIRED = {"job_id", "title", "company", "status"}


class JobStore:
    """Read/write ``jobStatusTable`` and the per-job description cache."""

    def __init__(self, path: Path, details_dir: Path, root: Path) -> None:
        self.table = CsvTable(path, JOB_FIELDS)
        self.details_dir = details_dir
        self.root = root

    @classmethod
    def from_config(cls, config: Config) -> JobStore:
        return cls(
            config.resolve_path(config.paths.job_status_table),
            config.job_details_dir,
            config.root,
        )

    def load(self) -> list[Job]:
        return [self._from_row(row) for row in self.table.read()]

    def save_all(self, jobs: list[Job]) -> None:
        self.table.write([self._to_row(job) for job in jobs])

    def ensure(self) -> None:
        self.table.ensure()
        self.details_dir.mkdir(parents=True, exist_ok=True)

    def get(self, job_id: str, jobs: list[Job] | None = None) -> Job | None:
        source = jobs if jobs is not None else self.load()
        return next((job for job in source if job.job_id == job_id), None)

    def require(self, job_id: str, jobs: list[Job] | None = None) -> Job:
        job = self.get(job_id, jobs)
        if job is None:
            raise DataError(f"Unknown job id: {job_id}")
        return job

    def write_description(self, job_id: str, text: str) -> str:
        self.details_dir.mkdir(parents=True, exist_ok=True)
        path = self.details_dir / f"{job_id}.txt"
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{job_id}.", suffix=".tmp", dir=str(self.details_dir), text=True
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
            raise DataError(f"Could not write job description {path}: {exc}") from exc
        return self._reference(path)

    def read_description(self, job: Job) -> str:
        if not job.description_path:
            return ""
        path = Path(job.description_path).expanduser()
        if not path.is_absolute():
            path = self.root / path
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _reference(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            return str(path.resolve())

    def _from_row(self, row: dict[str, str]) -> Job:
        missing = [field for field in _REQUIRED if not row.get(field, "").strip()]
        if missing:
            raise DataError(
                f"{self.table.path}: row is missing required column(s): {', '.join(missing)}"
            )
        try:
            status = parse_job_status(row.get("status", ""))
        except ValueError as exc:
            raise DataError(
                f"{self.table.path}: unknown job status {row.get('status')!r} "
                f"for {row.get('job_id')}. See docs/configuration.md for valid values."
            ) from exc
        extra = {key: value for key, value in row.items() if key not in JOB_FIELDS}
        return Job(
            job_id=row["job_id"].strip(),
            status=status,
            title=row.get("title", "").strip(),
            company=row.get("company", "").strip(),
            location=row.get("location", "").strip(),
            job_type=row.get("job_type", "").strip(),
            field=row.get("field", "").strip(),
            source=row.get("source", "").strip(),
            source_id=row.get("source_id", "").strip(),
            url=row.get("url", "").strip(),
            apply_url=row.get("apply_url", "").strip(),
            tags=split_list(row.get("tags", "")),
            include_matches=split_list(row.get("include_matches", "")),
            exclude_matches=split_list(row.get("exclude_matches", "")),
            posted_at=row.get("posted_at", "").strip(),
            first_seen=row.get("first_seen", "").strip(),
            last_seen=row.get("last_seen", "").strip(),
            applied_at=row.get("applied_at", "").strip(),
            notes=row.get("notes", ""),
            description_path=row.get("description_path", "").strip(),
            packet_path=row.get("packet_path", "").strip(),
            extra=extra,
        )

    def _to_row(self, job: Job) -> dict[str, str]:
        row = {
            "job_id": job.job_id,
            "status": job.status.value,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "job_type": job.job_type,
            "field": job.field,
            "source": job.source,
            "source_id": job.source_id,
            "url": job.url,
            "apply_url": job.apply_url,
            "tags": join_list(job.tags),
            "include_matches": join_list(job.include_matches),
            "exclude_matches": join_list(job.exclude_matches),
            "posted_at": job.posted_at,
            "first_seen": job.first_seen,
            "last_seen": job.last_seen or isoformat(),
            "applied_at": job.applied_at,
            "notes": job.notes,
            "description_path": job.description_path,
            "packet_path": job.packet_path,
        }
        row.update(job.extra)
        return row

"""Small, dependency-free CSV storage layer.

Tables are re-read on every command, written atomically, and retain columns the
user added by hand. This keeps manual edits safe while the CLI works.
"""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from ..utils.errors import DataError


def join_list(values: Iterable[str]) -> str:
    return "; ".join(value.strip() for value in values if value and value.strip())


def split_list(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


class CsvTable:
    """A CSV file with a stable core schema and user-added extra columns."""

    def __init__(self, path: Path, fields: list[str]) -> None:
        self.path = path
        self.fields = fields

    def exists(self) -> bool:
        return self.path.is_file()

    def ensure(self) -> None:
        if not self.exists():
            self.write([])

    def read(self) -> list[dict[str, str]]:
        if not self.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows: list[dict[str, str]] = []
                for raw in reader:
                    row: dict[str, str] = {}
                    for key, value in raw.items():
                        if key is None:
                            continue
                        row[str(key)] = "" if value is None else str(value)
                    if any(value.strip() for value in row.values()):
                        rows.append(row)
                return rows
        except OSError as exc:
            raise DataError(f"Could not read {self.path}: {exc}") from exc

    def write(self, rows: list[dict[str, str]]) -> None:
        fieldnames = list(self.fields)
        known = set(fieldnames)
        for row in rows:
            for key in row:
                if key not in known:
                    known.add(key)
                    fieldnames.append(key)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = ""
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=str(self.path.parent),
                text=True,
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({field: row.get(field, "") for field in fieldnames})
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, self.path)
        except OSError as exc:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            raise DataError(f"Could not write {self.path}: {exc}") from exc

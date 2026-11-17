"""Create user configuration and data tables from tracked examples."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config import Config
from ..storage.applications import ApplicationStore
from ..storage.jobs import JobStore
from ..storage.questions import BankStore, QuestionStore
from ..utils.errors import ConfigError

_COPIES = [
    ("user/user.example.toml", "user/user.toml"),
    ("user/urls.example.yaml", "user/urls.yaml"),
    ("user/extendedTags.example.yaml", "user/extendedTags.yaml"),
    ("user/resume.example.md", "user/resume.md"),
    (".env.example", ".env.local"),
]


def initialize_project(root: Path, *, force: bool = False) -> list[Path]:
    """Copy examples into place, create tables, and never invent secrets."""
    root = root.expanduser().resolve()
    (root / "user").mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    optional_templates = {".env.local"}
    for source_name, target_name in _COPIES:
        source = root / source_name
        target = root / target_name
        if target.exists() and not force:
            continue
        if not source.is_file():
            if target_name in optional_templates:
                continue
            raise ConfigError(f"Missing template {source}. Run init from the repository checkout.")
        if target.exists():
            backup = target.with_name(target.name + ".bak")
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)

    # Load the newly created config so all table paths are resolved exactly as
    # the application will resolve them.
    config = Config.load(root)
    config.ensure_directories()
    JobStore.from_config(config).ensure()
    ApplicationStore.from_config(config).ensure()
    QuestionStore.from_config(config).ensure()
    BankStore.from_config(config).ensure()
    written.extend(
        [
            config.resolve_path(config.paths.job_status_table),
            config.resolve_path(config.paths.job_applied_table),
            config.resolve_path(config.paths.questions_table),
            config.resolve_path(config.paths.question_bank_table),
        ]
    )
    return written

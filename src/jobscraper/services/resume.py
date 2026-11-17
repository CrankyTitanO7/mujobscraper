"""Resume loading for prompts and file-input autofill."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..utils.errors import ConfigError
from ..utils.text import truncate


def resume_path(config: Config) -> Path:
    return config.resume_path


def load_resume(config: Config, *, required: bool = False) -> str:
    """Read resume text from PDF, Markdown, or plain text."""
    path = resume_path(config)
    if not path.is_file():
        if required:
            raise ConfigError(
                f"Resume not found at {path}. Set [general].resume in user/user.toml."
            )
        return ""
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ConfigError("Reading PDF resumes requires pypdf") from exc
        try:
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # noqa: BLE001 - pypdf raises several types
            raise ConfigError(f"Could not read resume PDF {path}: {exc}") from exc
    elif suffix in {".txt", ".md", ".markdown", ""}:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Could not read resume {path}: {exc}") from exc
    else:
        raise ConfigError(
            f"Unsupported resume format {suffix!r}. Use PDF, Markdown, or plain text."
        )
    return truncate(text.strip(), config.llm.max_resume_chars)

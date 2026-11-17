"""Resume loading tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter

from jobscraper.config import Config
from jobscraper.services.resume import load_resume
from jobscraper.utils.errors import ConfigError


def test_load_markdown_resume(config: Config) -> None:
    text = load_resume(config)
    assert "Test Candidate" in text
    assert "machine learning" in text


def test_missing_resume_is_optional(config: Config) -> None:
    config.resume_path.unlink()
    assert load_resume(config) == ""
    with pytest.raises(ConfigError, match="Resume not found"):
        load_resume(config, required=True)


def test_unsupported_resume_format(config: Config) -> None:
    path = config.resume_path.with_suffix(".docx")
    path.write_bytes(b"not a resume")
    config.general.resume = "user/resume.docx"
    with pytest.raises(ConfigError, match="Unsupported resume format"):
        load_resume(config)
    path.unlink()


def test_load_pdf_resume(config: Config, tmp_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf = tmp_path / "resume.pdf"
    with pdf.open("wb") as handle:
        writer.write(handle)
    config.general.resume = str(pdf)
    assert load_resume(config) == ""


def test_resume_truncation(config: Config) -> None:
    config.llm.max_resume_chars = 10
    assert len(load_resume(config)) <= 10 + len("\n[... truncated ...]")

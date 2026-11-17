"""CLI smoke tests using Typer's runner."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from jobscraper.cli import app

runner = CliRunner()


def invoke(root: Path | None, *args: str):
    prefix = ["--root", str(root)] if root else []
    return runner.invoke(app, [*prefix, *args])


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "jobscraper" in result.output


def test_init_creates_config_and_tables(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    (tmp_path / "user").mkdir()
    for name in (
        "user.example.toml",
        "urls.example.yaml",
        "extendedTags.example.yaml",
        "resume.example.md",
    ):
        shutil.copyfile(source / "user" / name, tmp_path / "user" / name)
    shutil.copyfile(source / ".env.example", tmp_path / ".env.example")
    result = invoke(tmp_path, "init")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "user" / "user.toml").is_file()
    assert (tmp_path / "user" / "urls.yaml").is_file()
    assert (tmp_path / "user" / "jobStatusTable.csv").is_file()
    assert (tmp_path / "user" / "questions.csv").is_file()
    assert (tmp_path / ".env.local").is_file()


def test_init_is_non_destructive_without_force(project_root: Path) -> None:
    original = (project_root / "user" / "user.toml").read_text(encoding="utf-8")
    result = invoke(project_root, "init")
    assert result.exit_code == 0
    assert (project_root / "user" / "user.toml").read_text(encoding="utf-8") == original


def test_config_show_json(project_root: Path) -> None:
    result = invoke(project_root, "config", "show")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["general"]["name"] == "Big John"
    assert payload["resolved_season"] == "2026"


def test_jobs_list_json(project_root: Path, config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    result = invoke(project_root, "jobs", "list", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["job_id"] == job.job_id
    assert payload[0]["status"] == "new"


def test_track_and_applications_json(project_root: Path, config) -> None:
    from tests.conftest import make_job

    job = make_job(config)
    result = invoke(project_root, "track", job.job_id)
    assert result.exit_code == 0, result.output
    result = invoke(project_root, "applications", "list", "--json")
    payload = json.loads(result.output)
    assert payload[0]["job_id"] == job.job_id
    assert payload[0]["status"] == "applied"


def test_doctor_runs(project_root: Path) -> None:
    result = invoke(project_root, "doctor")
    assert result.exit_code == 0, result.output
    assert "config" in result.output
    assert "browser" in result.output


def test_questions_set_via_cli(project_root: Path, config, sample_form_html: str) -> None:
    from jobscraper.core.questionParse import scan_questions
    from tests.conftest import make_job

    job = make_job(config)
    questions = scan_questions(config, job.job_id, sample_form_html)
    full_name = next(question for question in questions if question.field_ref == "full_name")
    result = invoke(
        project_root,
        "questions",
        "set",
        full_name.question_id,
        "--answer",
        "Big John",
    )
    assert result.exit_code == 0, result.output
    assert "approved" in result.output


def test_help_lists_workflow() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("collect", "questions", "autofill", "track", "doctor"):
        assert command in result.output

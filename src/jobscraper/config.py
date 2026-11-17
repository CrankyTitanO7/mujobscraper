"""Typed configuration loading.

The editable user files stay in ``user/``. This module validates them, resolves
paths relative to the project root, and applies safe defaults. It never writes
secret values.
"""

from __future__ import annotations

import os
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils.errors import ConfigError

DEFAULT_USER_CONFIG = Path("user/user.toml")


def find_project_root(start: Path | None = None) -> Path:
    """Locate the project root by walking upward from ``start``.

    ``JOBSCRAPER_ROOT`` wins when set. Otherwise a directory containing
    ``user/user.toml`` is preferred, then the nearest ``pyproject.toml``, then
    the starting directory.
    """
    env_root = os.environ.get("JOBSCRAPER_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()

    current = (start or Path.cwd()).expanduser().resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / DEFAULT_USER_CONFIG).is_file():
            return candidate
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def load_environment(root: Path) -> None:
    """Load ``.env.local`` then ``.env`` without overriding existing values."""
    load_dotenv(root / ".env.local", override=False)
    load_dotenv(root / ".env", override=False)


class GeneralConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    current_employment: str = ""
    resume: str = "user/resume.md"
    links: dict[str, str] = Field(default_factory=dict)


class TagsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(default_factory=list)
    disclude: list[str] = Field(default_factory=list)
    match_mode: Literal["any", "all"] = "any"

    @field_validator("include", "disclude", mode="before")
    @classmethod
    def _split_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    urls: str = "user/urls.yaml"
    extended_tags: str = Field("user/extendedTags.yaml", alias="extendedTags")
    job_status_table: str = Field("user/jobStatusTable.csv", alias="jobStatusTable")
    job_applied_table: str = Field("user/jobAppliedTable.csv", alias="jobAppliedTable")
    questions_table: str = Field("user/questions.csv", alias="questionsTable")
    question_bank_table: str = Field("user/questionBank.csv", alias="questionBankTable")
    job_details_dir: str = Field("user/jobDetails", alias="jobDetailsDir")
    applications_dir: str = Field("user/applications", alias="applicationsDir")


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["auto", "openai", "ollama", "none"] = "auto"
    base_url: str = ""
    model: str = ""
    api_key_env: str = "JOBSCRAPER_LLM_API_KEY"
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    timeout: float = Field(120.0, gt=0)
    max_resume_chars: int = Field(12000, ge=0)
    adapt_reused_answers: bool = True
    refine_extraction: bool = True


class ScrapingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(100, ge=1)
    timeout: float = Field(30.0, gt=0)
    retries: int = Field(2, ge=0, le=10)
    request_delay_seconds: float = Field(0.5, ge=0.0)
    user_agent: str = "jobscraper/0.1"


class MatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    similarity_threshold: float = Field(0.82, ge=0.0, le=1.0)


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: str = ""
    require_approval: bool = True
    duplicate_guard: bool = True


class AutofillConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headless: bool = False
    keep_open: bool = True
    include_drafts: bool = False
    timeout_ms: int = Field(30000, ge=1000)
    browser_executable: str = ""


class Config(BaseModel):
    """Validated project configuration plus its resolved root."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    tags: TagsConfig = Field(default_factory=TagsConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    application: ApplicationConfig = Field(default_factory=ApplicationConfig)
    autofill: AutofillConfig = Field(default_factory=AutofillConfig)
    root: Path = Field(default=Path("."), exclude=True)

    @property
    def config_file(self) -> Path:
        return self.root / DEFAULT_USER_CONFIG

    @property
    def season(self) -> str:
        return self.application.season or str(datetime.now().year)

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.root / path).resolve()

    @property
    def urls_path(self) -> Path:
        return self.resolve_path(self.paths.urls)

    @property
    def extended_tags_path(self) -> Path:
        return self.resolve_path(self.paths.extended_tags)

    @property
    def resume_path(self) -> Path:
        return self.resolve_path(self.general.resume)

    @property
    def job_details_dir(self) -> Path:
        return self.resolve_path(self.paths.job_details_dir)

    @property
    def applications_dir(self) -> Path:
        return self.resolve_path(self.paths.applications_dir)

    def ensure_directories(self) -> None:
        self.job_details_dir.mkdir(parents=True, exist_ok=True)
        self.applications_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, root: Path | None = None) -> Config:
        root = (root or find_project_root()).expanduser().resolve()
        config_file = root / DEFAULT_USER_CONFIG
        if not config_file.is_file():
            raise ConfigError(
                f"Missing {config_file}. Run `uv run jobscraper init` to create user/ configs."
            )
        try:
            with config_file.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {config_file}: {exc}") from exc
        data["root"] = root
        try:
            return cls.model_validate(data)
        except Exception as exc:  # pydantic.ValidationError, intentionally wrapped
            raise ConfigError(f"Invalid configuration in {config_file}:\n{exc}") from exc

    def load_extended_tags(self) -> list[str]:
        path = self.extended_tags_path
        if not path.is_file():
            return []
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
        return _coerce_tag_list(raw, source=path)


def _coerce_tag_list(raw: Any, *, source: Path) -> list[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = raw.get("extendedTags") or raw.get("tags") or raw.get("extended_tags")
        if values is None:
            return []
        if not isinstance(values, list):
            raise ConfigError(f"{source}: tags must be a YAML list of strings")
    elif isinstance(raw, str):
        values = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        raise ConfigError(f"{source}: expected a list of tags")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ConfigError(f"{source}: tags must be strings, got {type(value).__name__}")
        if value.strip():
            result.append(value.strip())
    return result

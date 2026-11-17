"""Configuration for ``user/urls.yaml`` and construction of source adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..utils.errors import ConfigError


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True


class GreenhouseConfig(_Section):
    boards: list[str] = Field(default_factory=list)


class LeverConfig(_Section):
    companies: list[str] = Field(default_factory=list)


class ArbeitnowConfig(_Section):
    enabled: bool = False
    pages: int = Field(1, ge=1, le=20)
    search: str = ""


class RemoteOKConfig(_Section):
    enabled: bool = False
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _split_tags(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class GenericConfig(_Section):
    urls: list[str] = Field(default_factory=list)

    @field_validator("urls", mode="before")
    @classmethod
    def _one_url(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value


class SourcesConfig(BaseModel):
    """Validated representation of the user's source file."""

    model_config = ConfigDict(extra="forbid")

    greenhouse: GreenhouseConfig = Field(default_factory=GreenhouseConfig)
    lever: LeverConfig = Field(default_factory=LeverConfig)
    arbeitnow: ArbeitnowConfig = Field(default_factory=ArbeitnowConfig)
    remoteok: RemoteOKConfig = Field(default_factory=RemoteOKConfig)
    generic: GenericConfig = Field(default_factory=GenericConfig)

    def configured_names(self) -> list[str]:
        names: list[str] = []
        if self.greenhouse.enabled and self.greenhouse.boards:
            names.append("greenhouse")
        if self.lever.enabled and self.lever.companies:
            names.append("lever")
        if self.arbeitnow.enabled:
            names.append("arbeitnow")
        if self.remoteok.enabled:
            names.append("remoteok")
        if self.generic.enabled and self.generic.urls:
            names.append("generic")
        return names

    def has_job_sources(self) -> bool:
        return bool(self.configured_names())

    @classmethod
    def load(cls, path: Path) -> SourcesConfig:
        if not path.is_file():
            raise ConfigError(
                f"Missing source file {path}. Run `uv run jobscraper init` to create it."
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
        data = _normalize_legacy_shape(raw, path)
        try:
            return cls.model_validate(data)
        except Exception as exc:  # pydantic.ValidationError, intentionally wrapped
            raise ConfigError(f"Invalid sources in {path}:\n{exc}") from exc


def _normalize_legacy_shape(raw: Any, path: Path) -> dict[str, Any]:
    """Accept a plain URL list or the older ``urls:`` key."""
    if raw is None:
        return {}
    if isinstance(raw, list):
        if not all(isinstance(item, str) for item in raw):
            raise ConfigError(f"{path}: a URL list must contain only strings")
        return {"generic": {"urls": raw}}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a YAML mapping of job sources")
    data = dict(raw)
    if isinstance(data.get("sources"), dict):
        data = dict(data["sources"])
    legacy_urls = data.pop("urls", None)
    if legacy_urls:
        if isinstance(legacy_urls, str):
            legacy_urls = [legacy_urls]
        if not isinstance(legacy_urls, list):
            raise ConfigError(f"{path}: 'urls' must be a list of URLs")
        generic = data.get("generic") or {}
        if not isinstance(generic, dict):
            raise ConfigError(f"{path}: 'generic' must be a mapping")
        merged = list(generic.get("urls") or [])
        merged.extend(legacy_urls)
        generic["urls"] = merged
        data["generic"] = generic
    return data

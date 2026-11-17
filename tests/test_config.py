"""Configuration and source-file parsing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobscraper.config import Config, find_project_root
from jobscraper.sources.config import SourcesConfig
from jobscraper.utils.errors import ConfigError


def test_load_config_and_paths(config: Config, project_root: Path) -> None:
    assert config.root == project_root
    assert config.general.name == "Big John"
    assert config.tags.match_mode == "any"
    assert config.urls_path == project_root / "user" / "urls.yaml"
    assert config.resume_path.is_file()
    assert config.season == "2026"


def test_tags_accept_comma_separated_strings(tmp_path: Path, project_root: Path) -> None:
    text = (project_root / "user" / "user.toml").read_text(encoding="utf-8")
    text = text.replace(
        'include = ["internship", "machine learning", "bachelor", "bachelor\'s degree", "150k"]',
        'include = "internship, machine learning"',
    )
    (project_root / "user" / "user.toml").write_text(text, encoding="utf-8")
    config = Config.load(project_root)
    assert config.tags.include == ["internship", "machine learning"]


def test_extended_tags_are_loaded(config: Config) -> None:
    assert "remote" in config.load_extended_tags()


def test_missing_config_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="jobscraper init"):
        Config.load(tmp_path)


def test_find_project_root_walks_up(project_root: Path) -> None:
    nested = project_root / "a" / "b"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == project_root


def test_sources_config_and_legacy_url_list(project_root: Path) -> None:
    path = project_root / "user" / "urls.yaml"
    path.write_text("https://example.com/job/1\n", encoding="utf-8")
    # A bare string is a YAML scalar, not a list; use a list explicitly.
    path.write_text("- https://example.com/job/1\n", encoding="utf-8")
    sources = SourcesConfig.load(path)
    assert sources.generic.urls == ["https://example.com/job/1"]
    assert sources.configured_names() == ["generic"]


def test_sources_config_legacy_urls_key(project_root: Path) -> None:
    path = project_root / "user" / "urls.yaml"
    path.write_text(
        "urls:\n  - https://example.com/job/1\narbeitnow:\n  enabled: false\nremoteok:\n  enabled: false\n",
        encoding="utf-8",
    )
    sources = SourcesConfig.load(path)
    assert sources.generic.urls == ["https://example.com/job/1"]


def test_invalid_yaml_raises(project_root: Path) -> None:
    path = project_root / "user" / "urls.yaml"
    path.write_text("greenhouse: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        SourcesConfig.load(path)


def test_unknown_source_key_rejected(project_root: Path) -> None:
    path = project_root / "user" / "urls.yaml"
    path.write_text("linkedin:\n  enabled: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid sources"):
        SourcesConfig.load(path)

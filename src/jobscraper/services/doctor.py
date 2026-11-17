"""Environment and configuration diagnostics for ``jobscraper doctor``."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..llm.factory import build_provider, resolve_settings
from ..sources.config import SourcesConfig
from ..storage.applications import ApplicationStore
from ..storage.jobs import JobStore
from ..storage.questions import BankStore, QuestionStore
from ..utils.errors import JobscraperError


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    warning: bool = False


def run_doctor(config: Config, *, check_llm: bool = False) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("config", True, str(config.config_file)))

    try:
        sources = SourcesConfig.load(config.urls_path)
        names = sources.configured_names()
        if names:
            checks.append(Check("sources", True, ", ".join(names)))
        else:
            checks.append(
                Check(
                    "sources",
                    True,
                    "No sources enabled; edit user/urls.yaml before collecting.",
                    warning=True,
                )
            )
    except JobscraperError as exc:
        checks.append(Check("sources", False, str(exc)))

    try:
        config.ensure_directories()
        JobStore.from_config(config).ensure()
        ApplicationStore.from_config(config).ensure()
        QuestionStore.from_config(config).ensure()
        BankStore.from_config(config).ensure()
        checks.append(Check("tables", True, str(config.root / "user")))
    except Exception as exc:  # noqa: BLE001 - report instead of crashing doctor
        checks.append(Check("tables", False, str(exc)))

    resume = config.resume_path
    if resume.is_file():
        checks.append(Check("resume", True, str(resume)))
    else:
        checks.append(
            Check(
                "resume",
                True,
                f"Not found at {resume}; add one before autofilling.",
                warning=True,
            )
        )

    settings = resolve_settings(config)
    if settings.provider == "none" or not settings.model:
        checks.append(
            Check(
                "llm",
                True,
                "No provider configured; collection/filtering work, AI drafting is disabled.",
                warning=True,
            )
        )
    elif not check_llm:
        checks.append(
            Check(
                "llm",
                True,
                f"{settings.provider} / {settings.model} at {settings.base_url} "
                "(use --check-llm to test)",
            )
        )
    else:
        try:
            provider = build_provider(config)
            provider.complete("You are a health check.", "Reply with OK.", max_tokens=256)
            checks.append(Check("llm", True, f"{settings.provider} responded"))
        except Exception as exc:  # noqa: BLE001 - diagnostic output
            checks.append(Check("llm", False, str(exc)))

    browser = _browser_detail(config)
    checks.append(browser)
    return checks


def _browser_detail(config: Config) -> Check:
    configured = (
        config.autofill.browser_executable or os.environ.get("JOBSCRAPER_BROWSER_EXECUTABLE", "")
    ).strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return Check("browser", True, str(path))
        return Check("browser", False, f"Configured browser does not exist: {path}")
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return Check("browser", True, f"System browser: {found}")
    cache = Path.home() / ".cache" / "ms-playwright"
    if cache.is_dir() and any(cache.glob("chromium-*")):
        return Check("browser", True, f"Playwright cache: {cache}")
    return Check(
        "browser",
        True,
        "No browser detected yet. Run `uv run playwright install chromium` before autofill.",
        warning=True,
    )

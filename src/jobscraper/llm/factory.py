"""Choose and construct the configured LLM provider."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from ..config import Config
from ..utils.errors import LLMUnavailableError
from .base import LLMProvider
from .ollama import OllamaProvider
from .openai import OpenAICompatibleProvider

OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
OLLAMA_DEFAULT_BASE = "http://localhost:11434"


@dataclass(frozen=True)
class ProviderSettings:
    """Resolved provider settings, also useful for diagnostics."""

    provider: str
    base_url: str
    model: str
    api_key: str = ""

    @property
    def ready(self) -> bool:
        return self.provider != "none" and bool(self.model and self.base_url)


def resolve_settings(config: Config, env: Mapping[str, str] | None = None) -> ProviderSettings:
    env = env if env is not None else os.environ
    provider = (env.get("JOBSCRAPER_LLM_PROVIDER") or config.llm.provider).strip().casefold()
    base_url = (env.get("JOBSCRAPER_LLM_BASE_URL") or config.llm.base_url).strip()
    model = (env.get("JOBSCRAPER_LLM_MODEL") or config.llm.model).strip()
    api_key = (
        env.get(config.llm.api_key_env, "")
        or env.get("JOBSCRAPER_LLM_API_KEY", "")
        or env.get("OPENAI_API_KEY", "")
    ).strip()
    ollama_host = env.get("OLLAMA_HOST", "").strip().rstrip("/")

    if provider == "auto":
        if api_key:
            provider = "openai"
        elif ollama_host or "11434" in base_url or "ollama" in base_url.casefold():
            provider = "ollama"
        elif base_url and model:
            # An OpenAI-compatible local server may not need a key, but the
            # official endpoint always does. Avoid pretending it is ready.
            provider = "none" if "api.openai.com" in base_url.casefold() else "openai"
        else:
            provider = "none"

    if provider == "openai":
        base_url = base_url or OPENAI_DEFAULT_BASE
    elif provider == "ollama":
        base_url = ollama_host or base_url or OLLAMA_DEFAULT_BASE
    elif provider == "none":
        base_url = ""
        model = ""
    return ProviderSettings(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )


def build_provider(
    config: Config,
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> LLMProvider:
    """Return a provider or raise an actionable :class:`LLMUnavailableError`."""
    settings = resolve_settings(config, env)
    if settings.provider == "none":
        raise LLMUnavailableError(
            "No LLM provider configured. Add JOBSCRAPER_LLM_API_KEY and "
            "JOBSCRAPER_LLM_MODEL to .env.local, or run a local Ollama server "
            "and set JOBSCRAPER_LLM_PROVIDER=ollama / OLLAMA_HOST."
        )
    if not settings.model:
        raise LLMUnavailableError(
            "LLM model is not configured. Set JOBSCRAPER_LLM_MODEL or [llm].model."
        )
    if not settings.base_url:
        raise LLMUnavailableError("LLM base URL is not configured.")
    if settings.provider == "ollama":
        return OllamaProvider(
            base_url=settings.base_url,
            model=settings.model,
            timeout=config.llm.timeout,
            transport=transport,
        )
    return OpenAICompatibleProvider(
        base_url=settings.base_url,
        model=settings.model,
        api_key=settings.api_key,
        timeout=config.llm.timeout,
        transport=transport,
    )

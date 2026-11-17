"""Instantiate source adapters from validated configuration."""

from __future__ import annotations

from .arbeitnow import ArbeitnowSource
from .base import JobSource
from .config import SourcesConfig
from .generic import GenericSource
from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .remoteok import RemoteOKSource


def build_sources(config: SourcesConfig, *, request_delay: float = 0.0) -> list[JobSource]:
    """Instantiate enabled source adapters from validated configuration."""
    sources: list[JobSource] = []
    if config.greenhouse.enabled and config.greenhouse.boards:
        sources.append(GreenhouseSource(config.greenhouse.boards, delay=request_delay))
    if config.lever.enabled and config.lever.companies:
        sources.append(LeverSource(config.lever.companies, delay=request_delay))
    if config.arbeitnow.enabled:
        sources.append(
            ArbeitnowSource(
                pages=config.arbeitnow.pages,
                search=config.arbeitnow.search,
                delay=request_delay,
            )
        )
    if config.remoteok.enabled:
        sources.append(RemoteOKSource(config.remoteok.tags, delay=request_delay))
    if config.generic.enabled and config.generic.urls:
        sources.append(GenericSource(config.generic.urls, delay=request_delay))
    return sources

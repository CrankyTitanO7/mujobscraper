"""Structured logging setup for CLI commands."""

from __future__ import annotations

import logging

from rich.logging import RichHandler


def configure_logging(verbose: bool = False) -> None:
    """Configure readable logs on stderr, once per process."""
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger("jobscraper")
    root.setLevel(level)
    if root.handlers:
        for handler in root.handlers:
            handler.setLevel(level)
        return
    handler = RichHandler(show_path=False, rich_tracebacks=True, markup=False)
    handler.setLevel(level)
    root.addHandler(handler)
    root.propagate = False

"""Small parsing helpers shared by source adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..utils.matching import normalize_text
from ..utils.text import strip_html


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def name_of(value: Any) -> str:
    """Read ``name`` from a JSON-LD style object or string."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return first_text(value.get("name"), value.get("title"))
    return ""


def epoch_to_iso(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number > 10_000_000_000:  # milliseconds
        number /= 1000
    try:
        return datetime.fromtimestamp(number, tz=UTC).replace(microsecond=0).isoformat()
    except (OSError, OverflowError, ValueError):
        return ""


def clean_description(value: Any) -> str:
    return strip_html(first_text(value))


def search_matches(text: str, search: str) -> bool:
    """All whitespace-separated search terms must occur (case-insensitive)."""
    terms = [term for term in normalize_text(search).split() if term]
    if not terms:
        return True
    haystack = normalize_text(text)
    return all(term in haystack for term in terms)

"""Text normalization and HTML helpers."""

from __future__ import annotations

import re
from html import unescape

from bs4 import BeautifulSoup


def collapse_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


def html_to_text(html: str) -> str:
    """Convert HTML fragments from job feeds into readable plain text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def strip_html(text: str) -> str:
    """Remove tags from a string that may or may not contain HTML."""
    if "<" not in text or ">" not in text:
        return unescape(text or "").strip()
    return html_to_text(text)


def slugify(text: str, *, max_length: int = 60) -> str:
    """Create a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")
    return (slug or "item")[:max_length].rstrip("-") or "item"


def truncate(text: str, limit: int, *, suffix: str = "\n[... truncated ...]") -> str:
    """Limit text length without splitting a character."""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + suffix


def humanize_identifier(value: str) -> str:
    """Turn ``first_name`` / ``first-name`` into ``First name``."""
    name = re.sub(r"[_\-]+", " ", value or "").strip()
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return name[:1].upper() + name[1:] if name else ""

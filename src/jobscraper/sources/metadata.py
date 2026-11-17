"""Infer job type and industry field from feed text.

These are heuristics only; the values are shown in the editable jobs table and
can be corrected by hand. The LLM layer receives the corrected values.
"""

from __future__ import annotations

import re

_FIELD_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Machine Learning",
        (
            "machine learning",
            "deep learning",
            "ml engineer",
            "ai engineer",
            "artificial intelligence",
            "nlp",
            "computer vision",
            "llm",
        ),
    ),
    (
        "Data",
        (
            "data engineer",
            "data scientist",
            "data analyst",
            "analytics",
            "database",
            "etl",
            "warehouse",
        ),
    ),
    (
        "Software Engineering",
        (
            "software engineer",
            "developer",
            "backend",
            "frontend",
            "full stack",
            "fullstack",
            "platform engineer",
            "devops",
            "site reliability",
            "sre",
            "qa engineer",
        ),
    ),
    (
        "Design",
        ("designer", "ux", "ui designer", "graphic design", "product design"),
    ),
    ("Product", ("product manager", "product owner", "program manager", "project manager")),
    ("Marketing", ("marketing", "growth", "seo", "content", "brand", "communications")),
    ("Sales", ("sales", "account executive", "business development", "revenue")),
    ("Finance", ("finance", "financial", "accounting", "controller", "treasury")),
    ("Human Resources", ("human resources", "recruiter", "recruiting", "people operations")),
    ("Customer Support", ("customer support", "customer success", "support engineer", "help desk")),
    ("Operations", ("operations", "logistics", "supply chain", "office manager")),
    ("Legal", ("legal", "counsel", "paralegal", "compliance")),
    ("Research", ("research scientist", "researcher", "postdoc")),
]

_JOB_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("internship", ("intern", "internship", "co-op", "coop")),
    ("part-time", ("part-time", "part time")),
    ("contract", ("contract", "contractor", "freelance", "temporary", "temp")),
    ("full-time", ("full-time", "full time", "permanent")),
]


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in terms)


def _flatten(parts: tuple[object, ...]) -> str:
    values: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, str):
            values.append(part)
        elif isinstance(part, (list, tuple, set)):
            values.extend(str(item) for item in part if item is not None)
        else:
            values.append(str(part))
    return " ".join(value.casefold() for value in values if value)


def infer_field(*parts: object) -> str:
    """Infer a broad industry field, or ``Other`` when no rule matches."""
    text = _flatten(parts)
    for label, terms in _FIELD_RULES:
        if _has_any(text, terms):
            return label
    return "Other"


def infer_job_type(*parts: object) -> str:
    """Infer ``internship``, ``full-time``, ``part-time``, ``contract``, or empty."""
    text = _flatten(parts)
    for label, terms in _JOB_TYPE_RULES:
        if _has_any(text, terms):
            return label
    return ""


def merge_tags(*groups: object) -> list[str]:
    """Flatten tag-like values, normalize whitespace, and deduplicate."""
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        if group is None:
            continue
        if isinstance(group, str):
            values = [part.strip() for part in group.split(",")]
        elif isinstance(group, (list, tuple, set)):
            values = [str(item).strip() for item in group]
        else:
            values = [str(group).strip()]
        for value in values:
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
    return result

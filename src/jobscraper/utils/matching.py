"""Deterministic keyword and question matching.

Kept free of network and LLM calls so filtering and answer reuse are
predictable, fast, and easy to test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .text import collapse_whitespace

_WORD_EDGE = r"A-Za-z0-9"


def normalize_text(text: str) -> str:
    """Casefold and collapse punctuation/whitespace for loose comparisons."""
    value = collapse_whitespace(text).casefold()
    value = re.sub(r"[^a-z0-9+#.]+", " ", value)
    return collapse_whitespace(value)


def normalize_question(text: str) -> str:
    """Normalize a form question while preserving meaningful words."""
    value = normalize_text(text)
    value = re.sub(r"^(please\s+)?(enter|provide|upload|select|choose)\s+", "", value)
    return value.strip(" ?.:!-")


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(normalize_text(term))
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![{_WORD_EDGE}]){escaped}(?![{_WORD_EDGE}])")


def match_terms(text: str, terms: list[str]) -> list[str]:
    """Return the configured terms that occur in ``text``.

    Matching is case-insensitive and phrase-aware. Word edges are respected so
    ``senior`` does not match ``seniority``.
    """
    haystack = f" {normalize_text(text)} "
    matched: list[str] = []
    for term in terms:
        cleaned = normalize_text(term)
        if not cleaned:
            continue
        if _term_pattern(cleaned).search(haystack):
            matched.append(term)
    return matched


@dataclass(slots=True)
class FilterResult:
    """Outcome of applying include/exclude keyword rules to one job."""

    passed: bool
    include_matches: list[str] = field(default_factory=list)
    exclude_matches: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        if self.exclude_matches:
            return "excluded: " + ", ".join(self.exclude_matches)
        if not self.passed:
            return "no include keyword matched"
        return "matched"


def filter_text(
    text: str,
    include: list[str],
    exclude: list[str],
    *,
    mode: str = "any",
) -> FilterResult:
    """Apply include/exclude rules to a blob of job text.

    ``mode=any`` requires at least one include term; ``mode=all`` requires all
    of them. Exclusion always wins. An empty include list means "allow all".
    """
    includes = _dedupe(include)
    excludes = _dedupe(exclude)
    include_matches = match_terms(text, includes)
    exclude_matches = match_terms(text, excludes)
    if not includes:
        passed = True
    elif mode == "all":
        passed = len(include_matches) == len(includes)
    else:
        passed = bool(include_matches)
    if exclude_matches:
        passed = False
    return FilterResult(
        passed=passed,
        include_matches=include_matches,
        exclude_matches=exclude_matches,
    )


def _dedupe(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        key = normalize_text(term)
        if key and key not in seen:
            seen.add(key)
            result.append(term)
    return result


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "please",
    "the",
    "to",
    "we",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
    "you",
    "your",
    "us",
}


def question_tokens(text: str) -> set[str]:
    """Return meaningful tokens for question similarity."""
    return {token for token in normalize_question(text).split() if token not in _STOPWORDS}


def question_similarity(left: str, right: str) -> float:
    """Score how similar two questions are, from 0.0 to 1.0."""
    normalized_left = normalize_question(left)
    normalized_right = normalize_question(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    sequence = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = question_tokens(left)
    right_tokens = question_tokens(right)
    if not left_tokens or not right_tokens:
        return sequence
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = intersection / union
    containment = intersection / min(len(left_tokens), len(right_tokens))
    return max(sequence, (jaccard * 0.45) + (containment * 0.55))


def render_answer_template(answer: str, *, company: str, role: str, name: str = "") -> str:
    """Substitute placeholders allowed in editable bank answers."""
    values = {
        "company": company,
        "role": role,
        "name": name,
    }
    rendered = answer
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered

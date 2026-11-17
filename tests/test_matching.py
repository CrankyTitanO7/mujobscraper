"""Deterministic keyword and similarity tests."""

from __future__ import annotations

from jobscraper.utils.matching import (
    filter_text,
    match_terms,
    normalize_question,
    question_similarity,
    render_answer_template,
)


def test_word_boundary_avoids_seniority_false_positive() -> None:
    assert match_terms("Seniority is important", ["senior"]) == []
    assert match_terms("Senior Machine Learning Engineer", ["senior"]) == ["senior"]


def test_phrase_matching_and_case() -> None:
    matches = match_terms("This is a MACHINE   learning internship.", ["machine learning"])
    assert matches == ["machine learning"]


def test_include_any_and_exclusion_wins() -> None:
    result = filter_text(
        "Machine learning internship at Acme",
        ["internship", "data"],
        ["senior"],
        mode="any",
    )
    assert result.passed
    assert result.include_matches == ["internship"]

    result = filter_text(
        "Senior machine learning internship",
        ["internship"],
        ["senior"],
    )
    assert not result.passed
    assert result.exclude_matches == ["senior"]


def test_include_all_mode() -> None:
    result = filter_text(
        "machine learning internship", ["machine learning", "internship"], [], mode="all"
    )
    assert result.passed
    result = filter_text(
        "machine learning role", ["machine learning", "internship"], [], mode="all"
    )
    assert not result.passed


def test_empty_include_allows_all() -> None:
    result = filter_text("anything", [], ["senior"])
    assert result.passed
    assert not filter_text("senior role", [], ["senior"]).passed


def test_special_characters_are_escaped() -> None:
    assert match_terms("We use C++ daily", ["c++"]) == ["c++"]


def test_question_normalization_and_similarity() -> None:
    assert normalize_question("Please enter your full name?") == "your full name"
    high = question_similarity(
        "Why are you interested in this role?",
        "Why are you interested in this position?",
    )
    low = question_similarity("What is your name?", "Are you authorized to work in the US?")
    assert high > 0.8
    assert low < 0.5


def test_answer_template() -> None:
    text = render_answer_template(
        "I want to join {company} as a {role}. — {name}",
        company="Acme",
        role="ML Intern",
        name="Sam",
    )
    assert text == "I want to join Acme as a ML Intern. — Sam"

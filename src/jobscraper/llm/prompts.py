"""Prompt templates and tolerant JSON parsing for LLM responses."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

UNKNOWN_MARKER = "[[UNKNOWN]]"

SYSTEM_PROMPT = """You help a job seeker complete application forms accurately.
Use only facts supplied by the user. Never invent employers, dates, degrees,
authorizations, or legal status. Keep answers concise, specific, and in the
first person. Follow formatting instructions exactly.
"""


def _profile_block(profile: Mapping[str, Any], resume: str, max_resume_chars: int) -> str:
    links = profile.get("links") or {}
    lines = [
        f"Name: {profile.get('name', '')}",
        f"Email: {profile.get('email', '')}",
        f"Phone: {profile.get('phone', '')}",
        f"Address: {profile.get('address', '')}",
        f"Current employment: {profile.get('current_employment', '')}",
    ]
    for key, value in links.items():
        lines.append(f"{key}: {value}")
    if resume:
        excerpt = resume[:max_resume_chars] if max_resume_chars else resume
        lines.append("\nResume excerpt:\n" + excerpt)
    return "\n".join(line for line in lines if line.split(":", 1)[-1].strip())


def _job_block(job: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"Company: {job.get('company', '')}",
            f"Role: {job.get('title', '')}",
            f"Location: {job.get('location', '')}",
            f"Job type: {job.get('job_type', '')}",
            f"Field: {job.get('field', '')}",
            f"Tags: {', '.join(job.get('tags') or [])}",
            f"Description:\n{job.get('description', '')[:6000]}",
        ]
    )


def build_answer_prompt(
    *,
    profile: Mapping[str, Any],
    job: Mapping[str, Any],
    question: str,
    kind: str,
    options: list[str],
    reference_answer: str,
    resume: str,
    max_resume_chars: int,
) -> tuple[str, str]:
    """Build ``(system, user)`` prompts for one form question."""
    constraints = [
        "Answer the application question below.",
        "Return only the answer text, without a preamble, labels, or surrounding quotes.",
    ]
    if kind == "boolean":
        constraints.append("This is a true/false question. Return exactly `true` or `false`.")
    elif kind == "multiple_choice":
        constraints.append(
            "Choose exactly one of these options and return its text: " + ", ".join(options)
        )
    if reference_answer:
        constraints.append(
            "A previously approved answer is provided. Reuse it when it is still accurate; "
            "adapt company names, role names, and grammar to this job. Do not change factual "
            "claims."
        )
    constraints.append(
        f"If the supplied facts are insufficient to answer responsibly, return exactly "
        f"`{UNKNOWN_MARKER}`."
    )
    prompt = "\n\n".join(
        [
            "USER PROFILE\n" + _profile_block(profile, resume, max_resume_chars),
            "JOB\n" + _job_block(job),
            f"QUESTION\n{question}",
            f"PREVIOUSLY APPROVED ANSWER\n{reference_answer or '(none)'}",
            "RULES\n" + "\n".join(f"- {item}" for item in constraints),
        ]
    )
    return SYSTEM_PROMPT, prompt


def build_extraction_prompt(
    *,
    job: Mapping[str, Any],
    fields: list[dict[str, Any]],
) -> tuple[str, str]:
    """Build prompts that clean up heuristically extracted form fields."""
    field_json = json.dumps(fields, ensure_ascii=False, indent=2)
    prompt = "\n\n".join(
        [
            "JOB\n" + _job_block(job),
            "RAW FIELDS\n" + field_json,
            "TASK\n"
            "Identify the real application questions a candidate must answer. Drop search "
            "boxes, navigation, and hidden fields. Rewrite each label as a clear question. "
            "Preserve field_ref values exactly. Classify kind as free_text, boolean, "
            "multiple_choice, or file. For multiple_choice, include the available options.",
            "Return a JSON array only, using objects with keys: field_ref, question, kind, "
            "options. Return [] when there are no application questions.",
        ]
    )
    return SYSTEM_PROMPT, prompt


def parse_json_array(text: str) -> list[dict[str, Any]]:
    """Extract the first JSON array from a model response."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON array found in model response")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("Model response was not a JSON array")
    return [item for item in data if isinstance(item, dict)]


def is_unknown(text: str) -> bool:
    return UNKNOWN_MARKER in (text or "")

"""Greenhouse public job board adapter."""

from __future__ import annotations

import logging
from urllib.parse import quote

from ..models import JobPosting
from ..utils.errors import SourceError
from ..utils.http import HttpClient
from ..utils.text import html_to_text, humanize_identifier
from .base import JobSource
from .common import as_list, first_text
from .metadata import infer_field, infer_job_type, merge_tags

log = logging.getLogger(__name__)
API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def __init__(self, boards: list[str], *, delay: float = 0.0) -> None:
        self.boards = boards
        self.delay = delay

    def fetch(self, client: HttpClient) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        for index, board in enumerate(self.boards):
            if index:
                client.delay(self.delay)
            try:
                data = client.get_json(API.format(board=quote(board)))
            except Exception as exc:  # noqa: BLE001 - isolate a single board failure
                log.warning("Greenhouse board %s failed: %s", board, exc)
                errors.append(f"{board}: {exc}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                errors.append(f"{board}: unexpected response shape")
                continue
            for raw in data["jobs"]:
                posting = _parse_job(raw, board)
                if posting:
                    postings.append(posting)
        if not postings and errors:
            raise SourceError("Greenhouse failed for every board: " + "; ".join(errors))
        return postings


def _parse_job(raw: object, board: str) -> JobPosting | None:
    if not isinstance(raw, dict):
        return None
    title = first_text(raw.get("title"))
    if not title:
        return None
    metadata = [
        str(item.get("value", "")).strip()
        for item in as_list(raw.get("metadata"))
        if isinstance(item, dict) and str(item.get("value", "")).strip()
    ]
    departments = [
        str(item.get("name", "")).strip()
        for item in as_list(raw.get("departments"))
        if isinstance(item, dict)
    ]
    location = ""
    location_obj = raw.get("location")
    if isinstance(location_obj, dict):
        location = first_text(location_obj.get("name"))
    description = html_to_text(first_text(raw.get("content")))
    job_type = infer_job_type(title, *metadata, description)
    url = first_text(raw.get("absolute_url"))
    tags = merge_tags(departments, metadata, job_type)
    return JobPosting(
        title=title,
        company=first_text(raw.get("company_name"), humanize_identifier(board)) or board,
        source="greenhouse",
        source_id=first_text(raw.get("id"), url),
        location=location,
        description=description,
        url=url,
        apply_url=url,
        tags=tags,
        job_type=job_type,
        field=infer_field(title, description, tags),
        posted_at=first_text(raw.get("updated_at"), raw.get("created_at")),
    )

"""Lever public postings adapter."""

from __future__ import annotations

import logging
from urllib.parse import quote

from ..models import JobPosting
from ..utils.errors import SourceError
from ..utils.http import HttpClient
from ..utils.text import html_to_text, humanize_identifier
from .base import JobSource
from .common import epoch_to_iso, first_text
from .metadata import infer_field, infer_job_type, merge_tags

log = logging.getLogger(__name__)
API = "https://api.lever.co/v0/postings/{company}?mode=json"


class LeverSource(JobSource):
    name = "lever"

    def __init__(self, companies: list[str], *, delay: float = 0.0) -> None:
        self.companies = companies
        self.delay = delay

    def fetch(self, client: HttpClient) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        for index, company in enumerate(self.companies):
            if index:
                client.delay(self.delay)
            try:
                data = client.get_json(API.format(company=quote(company)))
            except Exception as exc:  # noqa: BLE001 - isolate a single company failure
                log.warning("Lever company %s failed: %s", company, exc)
                errors.append(f"{company}: {exc}")
                continue
            if not isinstance(data, list):
                errors.append(f"{company}: unexpected response shape")
                continue
            for raw in data:
                posting = _parse_job(raw, company)
                if posting:
                    postings.append(posting)
        if not postings and errors:
            raise SourceError("Lever failed for every company: " + "; ".join(errors))
        return postings


def _parse_job(raw: object, company_slug: str) -> JobPosting | None:
    if not isinstance(raw, dict):
        return None
    title = first_text(raw.get("text"))
    if not title:
        return None
    categories = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
    location = first_text(categories.get("location"))
    team = first_text(categories.get("team"))
    commitment = first_text(categories.get("commitment"))
    description = first_text(raw.get("descriptionPlain")) or html_to_text(
        first_text(raw.get("description"))
    )
    url = first_text(raw.get("hostedUrl"), raw.get("applyUrl"))
    tags = merge_tags(
        team,
        commitment,
        location,
        categories.get("allLocations") or [],
        infer_job_type(title, commitment, description),
    )
    job_type = commitment.casefold() if commitment else infer_job_type(title, description)
    return JobPosting(
        title=title,
        company=humanize_identifier(company_slug),
        source="lever",
        source_id=first_text(raw.get("id"), url),
        location=location,
        description=description,
        url=url,
        apply_url=first_text(raw.get("applyUrl"), url),
        tags=tags,
        job_type=job_type,
        field=infer_field(title, team, description, tags),
        posted_at=epoch_to_iso(raw.get("createdAt")),
    )

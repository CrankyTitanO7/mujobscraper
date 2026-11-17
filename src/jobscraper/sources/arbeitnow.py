"""Arbeitnow public job-board API adapter."""

from __future__ import annotations

from ..models import JobPosting
from ..utils.errors import SourceError
from ..utils.http import HttpClient
from ..utils.text import html_to_text
from .base import JobSource
from .common import epoch_to_iso, first_text, search_matches
from .metadata import infer_field, infer_job_type, merge_tags

API = "https://www.arbeitnow.com/api/job-board-api?page={page}"


class ArbeitnowSource(JobSource):
    name = "arbeitnow"

    def __init__(self, *, pages: int = 1, search: str = "", delay: float = 0.0) -> None:
        self.pages = pages
        self.search = search
        self.delay = delay

    def fetch(self, client: HttpClient) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for page in range(1, self.pages + 1):
            if page > 1:
                client.delay(self.delay)
            try:
                data = client.get_json(API.format(page=page))
            except Exception as exc:  # noqa: BLE001 - surface a concise source error
                raise SourceError(f"Arbeitnow page {page} failed: {exc}") from exc
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list) or not rows:
                break
            for raw in rows:
                posting = _parse_job(raw)
                if posting is None:
                    continue
                haystack = " ".join([posting.title, posting.description, " ".join(posting.tags)])
                if self.search and not search_matches(haystack, self.search):
                    continue
                postings.append(posting)
            links = data.get("links", {}) if isinstance(data, dict) else {}
            if not isinstance(links, dict) or not links.get("next"):
                break
        return postings


def _parse_job(raw: object) -> JobPosting | None:
    if not isinstance(raw, dict):
        return None
    title = first_text(raw.get("title"))
    if not title:
        return None
    description = html_to_text(first_text(raw.get("description")))
    job_types = [str(item) for item in raw.get("job_types") or [] if str(item).strip()]
    remote = bool(raw.get("remote"))
    tags = merge_tags(raw.get("tags"), job_types, "remote" if remote else "")
    location = first_text(raw.get("location")) or ("Remote" if remote else "")
    url = first_text(raw.get("url"))
    job_type = (job_types[0] if job_types else infer_job_type(title, description)).casefold()
    return JobPosting(
        title=title,
        company=first_text(raw.get("company_name")) or "Unknown",
        source="arbeitnow",
        source_id=first_text(raw.get("slug"), url),
        location=location,
        description=description,
        url=url,
        apply_url=url,
        tags=tags,
        job_type=job_type,
        field=infer_field(title, description, tags),
        posted_at=epoch_to_iso(raw.get("created_at")),
    )

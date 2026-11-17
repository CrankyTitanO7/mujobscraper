"""RemoteOK public feed adapter."""

from __future__ import annotations

from ..models import JobPosting
from ..utils.errors import SourceError
from ..utils.http import HttpClient
from ..utils.text import html_to_text
from .base import JobSource
from .common import epoch_to_iso, first_text
from .metadata import infer_field, infer_job_type, merge_tags

API = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    name = "remoteok"

    def __init__(self, tags: list[str] | None = None, *, delay: float = 0.0) -> None:
        self.tags = [tag.casefold() for tag in (tags or [])]
        self.delay = delay

    def fetch(self, client: HttpClient) -> list[JobPosting]:
        try:
            data = client.get_json(API)
        except Exception as exc:  # noqa: BLE001 - expose a short source error
            raise SourceError(f"RemoteOK failed: {exc}") from exc
        if not isinstance(data, list):
            raise SourceError("RemoteOK returned an unexpected response shape")
        postings: list[JobPosting] = []
        for raw in data:
            posting = _parse_job(raw)
            if posting is None:
                continue
            if self.tags and not set(self.tags) & {tag.casefold() for tag in posting.tags}:
                continue
            postings.append(posting)
        return postings


def _parse_job(raw: object) -> JobPosting | None:
    if not isinstance(raw, dict):
        return None
    title = first_text(raw.get("position"))
    if not title:
        return None
    description = html_to_text(first_text(raw.get("description")))
    tags = merge_tags(raw.get("tags"), "remote")
    url = first_text(raw.get("url"), raw.get("apply_url"))
    return JobPosting(
        title=title,
        company=first_text(raw.get("company")) or "Unknown",
        source="remoteok",
        source_id=first_text(raw.get("id"), url),
        location=first_text(raw.get("location")) or "Remote",
        description=description,
        url=url,
        apply_url=first_text(raw.get("apply_url"), url),
        tags=tags,
        job_type=infer_job_type(title, description, tags),
        field=infer_field(title, description, tags),
        posted_at=epoch_to_iso(raw.get("date")),
    )

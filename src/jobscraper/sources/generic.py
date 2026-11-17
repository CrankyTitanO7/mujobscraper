"""Generic static-page adapter using JSON-LD and page metadata."""

from __future__ import annotations

import logging

from ..models import JobPosting
from ..utils.errors import SourceError
from ..utils.http import HttpClient
from .base import JobSource
from .jsonld import extract_jobs

log = logging.getLogger(__name__)


class GenericSource(JobSource):
    name = "generic"

    def __init__(self, urls: list[str], *, delay: float = 0.0) -> None:
        self.urls = urls
        self.delay = delay

    def fetch(self, client: HttpClient) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        for index, url in enumerate(self.urls):
            if index:
                client.delay(self.delay)
            try:
                html = client.get_text(url)
            except Exception as exc:  # noqa: BLE001 - isolate a single page failure
                log.warning("Generic page %s failed: %s", url, exc)
                errors.append(f"{url}: {exc}")
                continue
            found = extract_jobs(html, url)
            if not found:
                errors.append(f"{url}: no JobPosting JSON-LD or usable page metadata")
            postings.extend(found)
        if not postings and errors:
            raise SourceError("Generic pages produced no jobs: " + "; ".join(errors))
        return postings

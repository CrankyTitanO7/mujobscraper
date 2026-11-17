"""Collect jobs from configured sources and apply deterministic filters."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Config
from ..models import Job, JobPosting, JobStatus, isoformat
from ..sources import SourcesConfig, build_sources
from ..sources.base import JobSource
from ..storage.jobs import JobStore
from ..utils.errors import ConfigError
from ..utils.http import HttpClient
from ..utils.matching import filter_text
from ..utils.text import collapse_whitespace

log = logging.getLogger(__name__)


@dataclass(slots=True)
class CollectionReport:
    discovered: int = 0
    added: int = 0
    updated: int = 0
    filtered_out: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def kept(self) -> int:
        return max(0, self.added + self.updated - self.filtered_out)


def include_terms(config: Config) -> list[str]:
    """Configured include keywords plus extended tags, in stable order."""
    terms = [*config.tags.include, *config.load_extended_tags()]
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        key = term.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(term.strip())
    return result


def job_filter_text(posting: JobPosting) -> str:
    return "\n".join(
        [
            posting.title,
            posting.company,
            posting.location,
            posting.job_type,
            posting.field,
            " ".join(posting.tags),
            posting.description,
        ]
    )


def collect_jobs(
    config: Config,
    sources_config: SourcesConfig,
    *,
    limit: int | None = None,
    source_names: list[str] | None = None,
    dry_run: bool = False,
    sources: list[JobSource] | None = None,
    client: HttpClient | None = None,
) -> CollectionReport:
    """Fetch, normalize, filter, and persist job postings."""
    names = {name.casefold() for name in (source_names or [])}
    selected = (
        sources
        if sources is not None
        else build_sources(sources_config, request_delay=config.scraping.request_delay_seconds)
    )
    if names:
        selected = [source for source in selected if source.name.casefold() in names]
    if not selected:
        configured = ", ".join(sources_config.configured_names()) or "none"
        raise ConfigError(
            f"No matching job sources. Configured: {configured}. "
            "Edit user/urls.yaml or pass a valid --source."
        )

    limit = limit if limit is not None else config.scraping.limit
    report = CollectionReport(dry_run=dry_run)
    include = include_terms(config)
    exclude = config.tags.disclude
    mode = config.tags.match_mode

    store = JobStore.from_config(config)
    existing_jobs = store.load()
    by_id = {job.job_id: job for job in existing_jobs}
    now = isoformat()
    seen_this_run: set[str] = set()

    owns_client = client is None
    http_client = client or HttpClient(
        timeout=config.scraping.timeout,
        retries=config.scraping.retries,
        user_agent=config.scraping.user_agent,
    )
    try:
        for source in selected:
            if report.discovered >= limit:
                break
            log.info("Fetching %s jobs", source.name)
            try:
                postings = source.fetch(http_client)
            except Exception as exc:  # noqa: BLE001 - one broken source must not stop the run
                message = f"{source.name}: {exc}"
                log.warning("Source failed: %s", message)
                report.errors.append(message)
                continue
            for posting in postings:
                if report.discovered >= limit:
                    break
                if posting.job_id in seen_this_run:
                    continue
                seen_this_run.add(posting.job_id)
                report.discovered += 1
                result = filter_text(job_filter_text(posting), include, exclude, mode=mode)
                if not result.passed:
                    report.filtered_out += 1
                existing = by_id.get(posting.job_id)
                if existing is None:
                    job = Job.from_posting(
                        posting,
                        status=JobStatus.NEW if result.passed else JobStatus.FILTERED_OUT,
                        include_matches=result.include_matches,
                        exclude_matches=result.exclude_matches,
                        now=now,
                    )
                    report.added += 1
                    by_id[job.job_id] = job
                    existing_jobs.append(job)
                else:
                    _update_existing(
                        existing,
                        posting,
                        passed=result.passed,
                        include_matches=result.include_matches,
                        exclude_matches=result.exclude_matches,
                        now=now,
                    )
                    report.updated += 1
                if not dry_run:
                    description = posting.description.strip()
                    job = by_id[posting.job_id]
                    if description:
                        job.description_path = store.write_description(job.job_id, description)
                    else:
                        job.description_path = ""
        if not dry_run:
            store.ensure()
            store.save_all(existing_jobs)
    finally:
        if owns_client:
            http_client.close()
    return report


def _update_existing(
    job: Job,
    posting: JobPosting,
    *,
    passed: bool,
    include_matches: list[str],
    exclude_matches: list[str],
    now: str,
) -> None:
    job.title = posting.title or job.title
    job.company = posting.company or job.company
    job.location = collapse_whitespace(posting.location)
    job.job_type = posting.job_type or job.job_type
    job.field = posting.field or job.field
    job.source = posting.source or job.source
    job.source_id = posting.source_id or job.source_id
    job.url = posting.url or job.url
    job.apply_url = posting.apply_url or job.apply_url
    job.tags = posting.tags or job.tags
    job.posted_at = posting.posted_at or job.posted_at
    job.last_seen = now
    job.include_matches = include_matches
    job.exclude_matches = exclude_matches
    if job.status in {
        JobStatus.APPLIED,
        JobStatus.SKIPPED,
        JobStatus.ANSWERED,
        JobStatus.ANSWERING,
        JobStatus.PACKET_READY,
    }:
        return
    job.status = JobStatus.NEW if passed else JobStatus.FILTERED_OUT


def refilter_jobs(config: Config, store: JobStore | None = None) -> tuple[int, int]:
    """Re-evaluate keyword filters for jobs that have not been applied to.

    Returns ``(kept, filtered_out)`` counts. Manual table edits are respected.
    """
    store = store or JobStore.from_config(config)
    jobs = store.load()
    include = include_terms(config)
    exclude = config.tags.disclude
    kept = filtered = 0
    changed = False
    for job in jobs:
        if job.status in {JobStatus.APPLIED, JobStatus.SKIPPED}:
            continue
        description = store.read_description(job)
        text = "\n".join(
            [
                job.title,
                job.company,
                job.location,
                job.job_type,
                job.field,
                " ".join(job.tags),
                description,
            ]
        )
        result = filter_text(text, include, exclude, mode=config.tags.match_mode)
        if (
            job.include_matches != result.include_matches
            or job.exclude_matches != result.exclude_matches
        ):
            changed = True
        job.include_matches = result.include_matches
        job.exclude_matches = result.exclude_matches
        if result.passed:
            kept += 1
            if job.status == JobStatus.FILTERED_OUT:
                job.status = JobStatus.NEW
                changed = True
        else:
            filtered += 1
            if job.status != JobStatus.FILTERED_OUT:
                job.status = JobStatus.FILTERED_OUT
                changed = True
    if changed:
        store.save_all(jobs)
    return kept, filtered


__all__ = [
    "CollectionReport",
    "collect_jobs",
    "include_terms",
    "job_filter_text",
    "refilter_jobs",
]

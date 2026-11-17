"""Extract ``JobPosting`` data from JSON-LD and static HTML pages."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..models import JobPosting
from ..utils.text import collapse_whitespace, html_to_text
from .common import as_list, clean_description, first_text, name_of
from .metadata import infer_field, infer_job_type, merge_tags


def extract_jobs(html: str, page_url: str, *, source: str = "generic") -> list[JobPosting]:
    """Return jobs found in JSON-LD, falling back to page metadata."""
    soup = BeautifulSoup(html, "html.parser")
    postings: list[JobPosting] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _walk_jsonld(data):
            posting = _posting_from_jsonld(item, page_url, source)
            if posting:
                postings.append(posting)
    if postings:
        return _dedupe(postings)
    fallback = _posting_from_metadata(soup, page_url, source)
    return [fallback] if fallback else []


def _walk_jsonld(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _walk_jsonld(item)
    elif isinstance(value, dict):
        types = as_list(value.get("@type"))
        if any(str(item).casefold() == "jobposting" for item in types):
            yield value
        graph = value.get("@graph")
        if graph:
            yield from _walk_jsonld(graph)


def _posting_from_jsonld(item: dict[str, Any], page_url: str, source: str) -> JobPosting | None:
    title = first_text(item.get("title"), item.get("name"))
    if not title:
        return None
    url = first_text(item.get("url"), item.get("sameAs"), page_url)
    identifier = item.get("identifier")
    if isinstance(identifier, dict):
        source_id = first_text(identifier.get("value"), identifier.get("name"))
    else:
        source_id = first_text(identifier)
    source_id = source_id or url
    company = name_of(item.get("hiringOrganization")) or _site_name(page_url)
    location = _location(item)
    employment = [str(value) for value in as_list(item.get("employmentType")) if value]
    description = clean_description(item.get("description"))
    tags = merge_tags(item.get("keywords"), employment)
    job_type = employment[0].casefold() if employment else infer_job_type(title, description)
    return JobPosting(
        title=title,
        company=company or "Unknown",
        source=source,
        source_id=source_id,
        location=location,
        description=description,
        url=url,
        apply_url=url,
        tags=tags,
        job_type=job_type,
        field=infer_field(title, description, tags),
        posted_at=first_text(item.get("datePosted")),
    )


def _location(item: dict[str, Any]) -> str:
    if str(item.get("jobLocationType", "")).casefold() == "telecommute":
        return "Remote"
    locations = as_list(item.get("jobLocation"))
    parts: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            parts.append(str(location))
            continue
        address = location.get("address", location)
        if isinstance(address, dict):
            locality = first_text(address.get("addressLocality"))
            region = first_text(address.get("addressRegion"))
            country = address.get("addressCountry")
            country_text = name_of(country) if isinstance(country, dict) else first_text(country)
            joined = ", ".join(part for part in (locality, region, country_text) if part)
            if joined:
                parts.append(joined)
        elif address:
            parts.append(str(address))
    return "; ".join(dict.fromkeys(parts))


def _posting_from_metadata(soup: BeautifulSoup, page_url: str, source: str) -> JobPosting | None:
    def meta(*keys: str) -> str:
        for key in keys:
            tag = soup.find("meta", attrs={"property": key}) or soup.find(
                "meta", attrs={"name": key}
            )
            if tag and tag.get("content"):
                return collapse_whitespace(str(tag["content"]))
        return ""

    title = meta("og:title", "twitter:title")
    if not title:
        heading = soup.find("h1")
        title = collapse_whitespace(heading.get_text(" ")) if heading else ""
    if not title:
        title_tag = soup.find("title")
        title = collapse_whitespace(title_tag.get_text(" ")) if title_tag else ""
    if not title:
        return None
    # Avoid treating obvious listing/search pages as a single job.
    if title.casefold().strip() in {"jobs", "careers", "job search", "open positions"}:
        return None
    company = meta("og:site_name") or _site_name(page_url)
    description = meta("og:description", "description")
    if not description:
        main = soup.find("main") or soup.find("article") or soup.body
        description = html_to_text(str(main))[:20000] if main else ""
    url = meta("og:url") or page_url
    return JobPosting(
        title=title,
        company=company or "Unknown",
        source=source,
        source_id=url,
        location=meta("og:locality"),
        description=description,
        url=url,
        apply_url=url,
        tags=[],
        job_type=infer_job_type(title, description),
        field=infer_field(title, description),
    )


def _site_name(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    return host.removeprefix("www.")


def _dedupe(postings: list[JobPosting]) -> list[JobPosting]:
    seen: set[str] = set()
    result: list[JobPosting] = []
    for posting in postings:
        if posting.job_id in seen:
            continue
        seen.add(posting.job_id)
        result.append(posting)
    return result

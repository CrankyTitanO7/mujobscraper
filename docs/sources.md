# Job sources

Sources are configured in `user/urls.yaml` and loaded by
`src/jobscraper/sources/config.py`. Each adapter returns normalized
`JobPosting` objects; collection, filtering, and storage are source-agnostic.

## Supported adapters

| Adapter | Config key | What it uses | Auth |
| --- | --- | --- | --- |
| Greenhouse | `greenhouse.boards` | Public board API: `boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` | None |
| Lever | `lever.companies` | Public postings API: `api.lever.co/v0/postings/{company}?mode=json` | None |
| Arbeitnow | `arbeitnow` | Public job-board API with pagination and optional search | None |
| RemoteOK | `remoteok` | Public feed at `remoteok.com/api`, optional tag filter | None |
| Generic | `generic.urls` | Static HTML pages with JSON-LD `JobPosting`, or OpenGraph metadata | None |

LinkedIn and Indeed listing scrapers are intentionally absent: they are
anti-bot heavy, fragile, and restricted by their terms of service. You can still
add an individual public posting URL to `generic.urls` if that page exposes
JSON-LD, or apply to those sites manually.

## `user/urls.yaml`

A complete example:

```yaml
greenhouse:
  enabled: true
  boards: []          # e.g. [stripe, figma]

lever:
  enabled: true
  companies: []       # e.g. [plaid]

arbeitnow:
  enabled: true
  pages: 1            # 1–20
  search: ""          # all whitespace-separated terms must appear

remoteok:
  enabled: true
  tags: []            # empty means no tag filter

generic:
  enabled: true
  urls: []            # individual static posting URLs
```

Notes:

- Omitted `arbeitnow` and `remoteok` sections are **disabled** by default. The
  example file enables them explicitly for a broad public feed.
- `greenhouse`, `lever`, and `generic` only run when they are enabled and have
  at least one board/company/URL.
- `enabled: false` disables a section even if it is populated.
- Unknown keys and unknown top-level sections are rejected, so typos fail
  loudly instead of silently doing nothing.
- A bare YAML list of URLs is accepted as shorthand for `generic.urls`:
  ```yaml
  - https://example.com/careers/ml-engineer
  ```
- The legacy `urls:` key is merged into `generic.urls` for compatibility.

Get board and company tokens from the public careers URLs:

- `https://boards.greenhouse.io/<board>` → `boards: [<board>]`
- `https://jobs.lever.co/<company>` → `companies: [<company>]`

## What adapters produce

Every posting is normalized to:

| Field | Source |
| --- | --- |
| `title`, `company`, `description` | Provider fields, HTML converted to text. |
| `location` | Provider location, or `Remote` where applicable. |
| `source`, `source_id` | Adapter name and provider ID (falling back to URL). |
| `url`, `apply_url` | Posting and application links. |
| `tags` | Departments, metadata, job types, `remote`, keywords. |
| `job_type` | Provider commitment/employment type or a text heuristic. |
| `field` | Broad industry heuristic (Machine Learning, Data, Software Engineering, …). |
| `posted_at` | ISO-8601 when the provider supplies a date. |

`job_type` and `field` are heuristics designed for filtering and grouping. Edit
the CSV row if a guess is wrong; later commands use the corrected value.

Job IDs are deterministic: the same source ID (or URL, or normalized
company/title/location) always produces the same `job_id`. Re-running collection
updates existing rows instead of duplicating them, and preserves statuses such
as `applied` or `packet_ready`.

## Generic pages and JSON-LD

`generic` fetches raw HTML (it does not execute JavaScript). It looks for
`<script type="application/ld+json">` blocks containing `JobPosting` objects,
including `@graph` containers. It reads:

- `title` / `name`
- `hiringOrganization.name`
- `jobLocation.address` (locality, region, country)
- `jobLocationType: "telecommute"` → `Remote`
- `employmentType`
- `description` (HTML stripped)
- `datePosted`
- `url` / `sameAs`
- `identifier.value`

If no JSON-LD is found, it falls back to OpenGraph metadata (`og:title`,
`og:site_name`, `og:description`, `og:url`), then to the first `<h1>` or the
page `<title>`. Obvious listing pages titled "Jobs", "Careers", "Job search", or
"Open positions" are ignored.

For JavaScript-rendered forms, save the rendered HTML from your browser or use
the live autofill browser. Collection of dynamic listing pages is out of scope.

## Errors and partial failures

- A single Greenhouse board, Lever company, or generic URL failure is logged and
  skipped; the adapter still returns results from the others.
- An adapter raises `SourceError` only if every configured board/company/URL
  failed, or the response shape is unusable.
- `collect_jobs` catches adapter errors per source, records them in the report,
  and continues with the next source. The CLI prints them as warnings.
- `--dry-run` fetches and filters but writes no tables, descriptions, or files.

Keep `request_delay_seconds` reasonable (default `0.5`) and respect each
provider's terms and rate limits.

## Adding an adapter

1. Create `src/jobscraper/sources/<name>.py` with a class extending `JobSource`
   and implementing `fetch(client: HttpClient) -> list[JobPosting]`.
2. Normalize fields in the adapter. Use helpers from `sources/common.py`,
   `sources/metadata.py`, and `utils/text.py` instead of duplicating parsing.
3. Add a Pydantic section to `sources/config.py` and a branch in
   `sources/registry.py`.
4. Add offline tests using `httpx.MockTransport` in `tests/test_sources.py`.
5. Document the config keys here and in `user/urls.example.yaml`.

Adapters should never require credentials, never submit forms, and should fail
soft for individual boards so one bad token does not break a collection run.

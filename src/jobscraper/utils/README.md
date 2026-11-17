# `utils`

Small, dependency-light helpers shared across the package.

| Module | Purpose |
| --- | --- |
| `errors.py` | `JobscraperError` base plus config, data, source, fetch, LLM, and browser errors. |
| `http.py` | `HttpClient` wrapper around `httpx` with conservative retries and URL validation. |
| `text.py` | Whitespace/HTML cleaning, slugify, truncation, identifier humanization. |
| `matching.py` | Keyword filtering, question normalization/similarity, answer placeholders. |
| `logging.py` | Rich stderr logging configured once per process. |

## `errors.py`

Expected failures inherit from `JobscraperError`. The CLI catches that base and
prints a single readable message instead of a traceback. Unexpected exceptions
still surface normally for debugging.

## `http.py`

- Injects an `httpx` transport for tests.
- Retries transport errors, `429`, and `500/502/503/504` with small backoff.
- Honors `Retry-After` (capped at 30 seconds).
- Raises `FetchError` with the URL and a short body excerpt on failure.
- Rejects non-HTTP(S) URLs.
- Supports JSON and text helpers plus an explicit inter-request delay.

## `matching.py`

- `match_terms` is case-insensitive, phrase-aware, and respects word edges.
- `filter_text` implements include `any`/`all` and exclusion-wins semantics.
- `normalize_question` strips polite prefixes and punctuation for comparison.
- `question_similarity` combines sequence similarity with token overlap.
- `render_answer_template` substitutes only `{company}`, `{role}`, and `{name}`.

## `text.py`

HTML is converted with BeautifulSoup, with scripts/styles removed. `slugify` and
`truncate` are used for packet folders and prompt limits; `humanize_identifier`
turns `first_name` into `First name`.

## `logging.py`

`configure_logging(verbose)` sets the `jobscraper` logger to INFO or DEBUG and
adds a `RichHandler` once. Logs go to stderr; command output stays on stdout so
`--json` remains parseable.

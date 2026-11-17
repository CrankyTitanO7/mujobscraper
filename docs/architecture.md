# Architecture

jobscraper is a batch-oriented pipeline. Each command loads editable files,
performs one stage, and writes back atomically. There is no long-running server
and no hidden database.

## Data flow

```
user/urls.yaml ──► sources/ ──► JobPosting ──► core/webscraper ──► jobStatusTable.csv
                                                      │                 │
                                                      ▼                 ▼
                                               user/jobDetails/   deterministic filter
                                                                        │
application form HTML ──► browser/forms ──► core/questionParse ──► questions.csv
                                                      │                 │
                                        questionBank.csv ◄──── approve  │
                                                      │                 ▼
                                                      └───────────► packet generation
                                                                        │
                                                                        ▼
                                                              user/applications/
                                                                        │
                                                                        ▼
                                                          autofill (browser, no submit)
                                                                        │
                                                                        ▼
                                                        jobAppliedTable.csv (track)
```

A typical loop is:

1. **Collect** — adapters fetch postings and normalize them into `JobPosting`
   records. `core/webscraper.collect_jobs` deduplicates by `job_id`, applies
   keyword filters, caches descriptions, and writes `jobStatusTable.csv`.
2. **Scan** — `core/questionParse.scan_questions` extracts form controls from
   HTML, stores them in `questions.csv`, and reuses compatible bank answers.
3. **Draft/approve** — the LLM drafts only unanswered questions. Approval writes
   the answer into `questionBank.csv`, so similar future questions can reuse it.
4. **Packet** — `core/questionSubmit.generate_packet` renders a Markdown review
   packet. The job becomes `packet_ready` only when no question is pending.
5. **Autofill** — `browser/autofill.build_fill_plan` maps saved answers onto
   controls and optionally fills them. Submission is never automated.
6. **Track** — `core/questionSubmit.track_application` records the application,
   updates the job, and guards against same-season duplicates.
7. **Refresh** — `core/updateData.refresh_statuses` recomputes job statuses from
   the tables after manual edits.

## Module map

| Module | Responsibility |
| --- | --- |
| `cli.py` | Typer app, command wiring, Rich tables/JSON output, error handling. |
| `config.py` | Root discovery, `.env` loading, Pydantic models for `user.toml`, path resolution. |
| `models.py` | Dataclasses and enums: `JobPosting`, `Job`, `Question`, `BankAnswer`, `Application`; ID generation; status parsers. |
| `sources/config.py` | Validated `urls.yaml`, legacy shape normalization. |
| `sources/registry.py` | Builds enabled adapters from source config. |
| `sources/*.py` | One adapter per provider plus shared JSON-LD/metadata helpers. |
| `storage/csv_store.py` | Atomic CSV read/write, BOM tolerance, extra-column preservation. |
| `storage/jobs.py` | `jobStatusTable` repository and description cache. |
| `storage/questions.py` | `questions.csv` and `questionBank.csv` repositories. |
| `storage/applications.py` | `jobAppliedTable.csv` repository and duplicate lookup. |
| `core/webscraper.py` | Collection, filtering, re-filtering, include-term merging. |
| `core/questionParse.py` | Field extraction orchestration, bank reuse, LLM drafting, answer validation, approval. |
| `core/questionSubmit.py` | Packet rendering, status updates, tracking, application updates. |
| `core/updateData.py` | Status reconciliation from questions and applications. |
| `browser/forms.py` | BeautifulSoup form parsing; labels, kinds, options, DOM indices. |
| `browser/autofill.py` | Fill planning, Playwright launch/fill, screenshots, no submit. |
| `llm/factory.py` | Provider resolution (`auto`, `openai`, `ollama`, `none`). |
| `llm/openai.py`, `llm/ollama.py` | HTTP chat clients. |
| `llm/prompts.py` | Prompt builders and tolerant JSON parsing. |
| `services/init.py` | Non-destructive project initialization. |
| `services/doctor.py` | Diagnostics for config, sources, tables, resume, LLM, browser. |
| `services/resume.py` | Resume loading from PDF, Markdown, or text. |
| `utils/` | Errors, HTTP retries, text normalization, keyword/question matching, logging. |

## Status model

### Job statuses

| Status | Meaning |
| --- | --- |
| `new` | Collected and passed filters; no questions yet. |
| `filtered_out` | Excluded by keywords or missing required include terms. |
| `answering` | Questions exist, at least one is not terminal. |
| `answered` | All questions are `approved`, `reused`, or `skipped`. |
| `packet_ready` | A packet was generated without pending questions. |
| `applied` | An application row exists or `track` was run. |
| `skipped` | Manually abandoned. |

`applied` wins over every other state. `skipped` and `filtered_out` are sticky
until the user changes them or re-filters. Collection updates metadata but does
not move jobs backwards out of `answered`, `answering`, `packet_ready`,
`applied`, or `skipped`.

### Question statuses

| Status | Meaning |
| --- | --- |
| `unanswered` | Needs an answer. |
| `needs_review` | A draft or adapted answer exists but is not trusted yet. |
| `approved` | Explicitly approved and copied to the bank. |
| `reused` | Filled from a bank answer without adaptation. |
| `skipped` | Deliberately ignored. |

Only `approved` and `reused` answers are autofilled by default; `--include-drafts`
also allows `needs_review`.

## Design principles

- **Human-readable state.** CSVs are the source of truth. Files are re-read on
  every command, so edits made in a spreadsheet are picked up immediately.
- **Atomic writes.** Tables and detail files are written to a temp file in the
  same directory, fsynced, then replaced. Extra user columns survive round trips.
- **No hidden side effects.** Collection is `--dry-run`-able; autofill is a plan
  unless `--fill` is passed; submission is never automated.
- **Deterministic first.** Keyword filtering and bank matching are local,
  testable, and independent of any model. The LLM is an optional drafting aid.
- **Dependency injection for testing.** HTTP transports, LLM providers, and
  source lists can be injected so the test suite runs offline.
- **Fail soft per source.** One broken adapter does not abort a collection run;
  its error is reported and other sources continue.
- **Actionable errors.** Expected failures raise `JobscraperError` subclasses and
  are printed by the CLI without a traceback.

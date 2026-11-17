# `core`

Workflow orchestration. These modules combine sources, storage, the LLM, and the
browser, but contain no CLI formatting.

| Module | Public API | Purpose |
| --- | --- | --- |
| `webscraper.py` | `collect_jobs`, `refilter_jobs`, `include_terms`, `job_filter_text`, `CollectionReport` | Fetch, normalize, filter, deduplicate, persist jobs and descriptions. |
| `questionParse.py` | `scan_questions`, `draft_answers`, `set_answer`, `approve_question`, `skip_question`, `best_bank_match`, normalizers | Extract questions, reuse bank answers, draft with an LLM, validate and approve answers. |
| `questionSubmit.py` | `generate_packet`, `render_packet`, `track_application`, `update_application` | Render review packets, create/update application history, enforce duplicate protection. |
| `updateData.py` | `refresh_statuses` | Recompute job statuses from questions and applications. |

## Collection

`collect_jobs` accepts optional injected `sources` and `client` for tests, a
`limit`, `source_names`, and `dry_run`. It:

1. Selects adapters from `SourcesConfig`.
2. Fetches each source, isolating failures.
3. Deduplicates by deterministic `job_id` within the run.
4. Applies include/exclude filters (extended tags merged into includes).
5. Updates existing metadata without regressing terminal statuses.
6. Writes description files and `jobStatusTable.csv` unless dry-running.

`refilter_jobs` re-evaluates non-applied jobs after keyword edits and flips
between `new` and `filtered_out`.

## Questions

`scan_questions` parses HTML, merges with existing rows by `field_ref` or
`question_id`, auto-approves resume uploads, and reuses compatible bank answers.
`draft_answers` requires a provider and only touches unresolved questions.
`set_answer` validates booleans and choices, then upserts the bank on approval.
Every mutation calls `refresh_statuses` for that job.

## Packets and tracking

`generate_packet` writes
`user/applications/<company>-<title>-<job_id>/application.md` and marks the job
`packet_ready` only when no question is pending. `track_application` creates or
updates one row per job/season, marks the job `applied`, and rejects a duplicate
company/title in the same season unless `force=True`.

## Status precedence

1. An application row → `applied`.
2. `skipped`/`filtered_out` stay put.
3. Questions exist → `answering` or `answered` when all are terminal.
4. Otherwise the job remains `new`.

`packet_ready` is set by packet generation and preserved until an application or
manual change supersedes it.

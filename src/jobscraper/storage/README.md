# `storage`

CSV-backed persistence. Tables are the source of truth and are re-read on every
command so manual edits take effect immediately.

| Module | Purpose |
| --- | --- |
| `csv_store.py` | `CsvTable`: atomic read/write, BOM tolerance, extra-column preservation, semicolon list helpers. |
| `jobs.py` | `JobStore`: `jobStatusTable.csv` plus the `user/jobDetails/` description cache. |
| `questions.py` | `QuestionStore` (`questions.csv`) and `BankStore` (`questionBank.csv`). |
| `applications.py` | `ApplicationStore`: `jobAppliedTable.csv` and duplicate lookup. |

## Guarantees

- **Atomic writes.** A temp file is created in the target directory, written,
  fsynced, chmodded where supported, then `os.replace`d over the target.
- **Manual columns survive.** Unknown columns are appended to the schema and
  preserved on the next write.
- **Blank rows are ignored.** A row must have at least one non-empty cell.
- **UTF-8 with or without BOM.** Output is UTF-8 without a BOM.
- **Readable lists.** Multi-value fields use `; ` as the separator.
- **Validation on read.** Missing required columns/IDs and invalid enum values
  raise `DataError` with the file and row context.

## Repositories

Each store follows the same pattern:

```python
store = JobStore.from_config(config)
jobs = store.load()
job = store.require(job_id, jobs)
jobs.append(job)
store.save_all(jobs)
```

`ensure()` creates the table header and required directories. `from_config`
resolves paths through `Config`, so `--root` and custom `[paths]` work
everywhere.

## Timestamps and IDs

Timestamps are ISO-8601 UTC with second precision. IDs are deterministic short
hashes (`job_…`, `q_…`, `a_…`, `app_…`) so repeated collection or rescans update
rows instead of creating duplicates.

See [docs/configuration.md](../../../docs/configuration.md) for every column and
status value.

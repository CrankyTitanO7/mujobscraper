# `user/` — your editable data

Everything personal lives here. Tracked files end in `.example.*`; the real
files are gitignored. `jobscraper init` copies examples into place without
overwriting existing files.

## Files

| File | Tracked? | Purpose |
| --- | --- | --- |
| `user.toml` | No | Profile, keywords, paths, LLM, and autofill settings. Created from `user.example.toml`. |
| `urls.yaml` | Yes (starter) | Enabled job sources. Edit it; the starter enables Arbeitnow and RemoteOK. |
| `extendedTags.yaml` | Yes (starter) | Extra include keywords merged with `[tags].include`. |
| `resume.md` | No | Your resume (PDF/text also supported). Created from `resume.example.md`. |
| `jobStatusTable.csv` | No | Discovered jobs, metadata, filters, and statuses. |
| `questions.csv` | No | Per-job form questions and answers. |
| `questionBank.csv` | No | Reusable approved answers. |
| `jobAppliedTable.csv` | No | Application history and progress. |
| `jobDetails/` | No | Cached plain-text job descriptions. |
| `applications/` | No | Generated Markdown packets. |
| `parseEgToSet.py` | Yes | Compatibility wrapper for the old example-copy workflow; prefer `uv run jobscraper init`. |

## First-time setup

```bash
uv run jobscraper init
uv run jobscraper doctor
```

Then:

1. Replace `resume.md` with your real resume.
2. Fill in `[general]` in `user.toml`.
3. Adjust `[tags].include` / `[tags].disclude`.
4. Configure `urls.yaml`.
5. Add LLM credentials to `.env.local` at the project root, if desired.

## Editing by hand

- CSVs are re-read on every command; spreadsheet edits are fine.
- Keep the header row and required columns (`job_id`/`status`/`title`/`company`,
  `question_id`/`job_id`, `answer_id`, `application_id`).
- Lists use semicolons (`python; machine learning`).
- Extra columns you add are preserved.
- Statuses are validated when read; invalid values raise an error naming the row.
- Save as UTF-8 CSV. A BOM is tolerated.

Run `uv run jobscraper jobs refresh` after changing statuses or questions by hand
to reconcile job states.

## Reset

`init --force` backs up and replaces configs and resets table headers. It does
**not** delete descriptions or packets. Remove those directories explicitly if
you want a clean slate.

See [docs/configuration.md](../docs/configuration.md) for every column and
setting, and [docs/sources.md](../docs/sources.md) for `urls.yaml`.

# Troubleshooting

Start with:

```bash
uv run jobscraper doctor
uv run jobscraper doctor --check-llm   # sends a tiny provider request
uv run jobscraper config show          # resolved settings, secrets masked
```

## Configuration

### `Missing .../user/user.toml`

You are outside a project root or have not initialized it. Run:

```bash
uv run jobscraper init
```

If your files live elsewhere, pass `--root /path/to/project` before the command
or set `JOBSCRAPER_ROOT`.

### `Invalid TOML` / `Invalid YAML`

The error names the file and line. Common causes:

- TOML: unquoted strings, missing commas inside lists, duplicate keys.
- YAML: tabs instead of spaces, unclosed brackets, a scalar where a mapping is
  expected.

`user/urls.yaml` must be a mapping of source sections, or a plain list of URLs
for generic pages. Compare with `user/urls.example.yaml`.

### `Invalid configuration ... Extra inputs are not permitted`

An unknown key was added to `user.toml` or `urls.yaml`. Fix the spelling or
remove the key; jobscraper rejects unknown keys so typos do not silently do
nothing.

### `.env.local` changes have no effect

- Confirm you are in the expected root: `uv run jobscraper config show` prints
  the config path.
- `.env.local` is loaded before `.env`, and neither overrides variables already
  set in the shell. Unset a conflicting exported variable or use `env -u NAME`.
- Restart the command; each CLI invocation reloads the environment.

## Collection

### `No matching job sources`

Every source is disabled or empty. Edit `user/urls.yaml`. At minimum enable one
of:

```yaml
arbeitnow:
  enabled: true
remoteok:
  enabled: true
```

or add a Greenhouse board, Lever company, or generic URL. `--source NAME`
further narrows the run, so make sure the name you pass is actually enabled.

### A source reports `HTTP 403`, `HTTP 429`, or timeouts

- Increase `[scraping].request_delay_seconds` (for example `1.0`).
- Lower `[scraping].limit`.
- Retry later; public APIs rate-limit and occasionally change shape.
- One source failing is not fatal. Other sources still run; the warning lists the
  failure.

### `no JobPosting JSON-LD or usable page metadata`

The generic adapter fetches static HTML only. If the page is rendered by
JavaScript, save the rendered HTML from your browser and scan it locally with
`questions scan --html ...`; collection of dynamic listing pages is out of
scope. Individual static postings usually expose OpenGraph metadata and work.

### Collected jobs are immediately `filtered_out`

Inspect `include_matches` and `exclude_matches` in `user/jobStatusTable.csv`.
Remember:

- Inclusion requires at least one include term in `any` mode.
- Exclusion always wins.
- Extended tags are includes, never excludes.
- An empty include list allows everything.

After editing keywords, run `uv run jobscraper filter` to re-evaluate jobs that
are not applied.

### A job disappeared or moved back to `new`

Collection updates metadata but does not move jobs out of `answering`,
`answered`, `packet_ready`, `applied`, or `skipped`. `filter` can move a job
between `new` and `filtered_out`. If you want a fresh decision, edit the status
in the CSV or run `jobs refresh`.

### Duplicate jobs

Job IDs are deterministic by source plus source ID/URL/company/title/location.
The same role from two different sources is intentionally two rows. The
application duplicate guard uses normalized company + title per season to catch
cross-source duplicates when tracking.

## LLM

### `No LLM provider configured`

AI features are optional. To enable them, edit `.env.local`:

```bash
JOBSCRAPER_LLM_PROVIDER=openai
JOBSCRAPER_LLM_BASE_URL=https://api.openai.com/v1
JOBSCRAPER_LLM_MODEL=gpt-4o-mini
JOBSCRAPER_LLM_API_KEY=sk-...
```

Then run `uv run jobscraper doctor --check-llm`.

For Ollama:

```bash
JOBSCRAPER_LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
JOBSCRAPER_LLM_MODEL=llama3.1
```

The model must already exist locally (`ollama pull llama3.1`); jobscraper never
downloads models.

### The official OpenAI endpoint is ignored without a key

This is intentional. `provider = "auto"` treats `api.openai.com` without a key as
unavailable instead of sending unauthenticated requests. Add a key or switch to a
local OpenAI-compatible server.

### `OpenAI-compatible request failed` / `Ollama request failed`

- Check the base URL and model name.
- Confirm the server is running (`curl http://localhost:11434/api/tags` for
  Ollama).
- Increase `[llm].timeout` for slow local models.
- `doctor --check-llm` prints the underlying error.

### OpenRouter free models return no text

The `openrouter/free` router can select reasoning models. jobscraper asks
OpenRouter to disable reasoning, and retries without that flag plus a larger
token budget when reasoning is mandatory. If a specific free model still spends
the whole response on hidden reasoning, set `JOBSCRAPER_LLM_MODEL` to a
specific non-reasoning free model from OpenRouter's model list. Base URLs with a
trailing `/chat/completions`, `/completions`, or `/responses` are normalized
automatically.

### Drafting says the AI could not answer

The model returned `[[UNKNOWN]]`, or the response was empty. Add more profile
or resume detail, answer manually with `questions set`, or lower the temperature.
Answers are never invented when the model declines.

## Questions and answers

### `questions scan` finds nothing

- The page may render fields with JavaScript. Save the rendered HTML and use
  `--html`, or use `autofill --save-questions`.
- The form may use hidden or custom controls, shadow DOM, or iframes, which are
  not parsed.
- Check the HTML actually contains `input`, `textarea`, or `select` elements.

### AI returned a non-boolean / non-matching answer

Drafts are saved as `needs_review` with a note. Boolean questions expect
yes/no/true/false; multiple-choice answers must match an option exactly. Fix with:

```bash
uv run jobscraper questions set QUESTION_ID --answer "No"
```

### A reused answer is wrong for this job

Reused answers are matched by similarity, not comprehension. Override it:

```bash
uv run jobscraper questions set QUESTION_ID --answer "Correct answer"
```

Approval updates the linked bank answer. If one bank answer is being reused too
broadly, make its question text more specific or archive it in
`user/questionBank.csv`.

### `Boolean answers must be true/false (or yes/no)`

Use one of `true`, `false`, `yes`, `no`, `y`, `n`, `1`, `0`, `authorized`, or
`not authorized`. The stored value is always `true` or `false`.

### `Answer must match one of: ...`

For select/radio questions, pass the exact option text (case-insensitive). Run
`questions list JOB_ID` to see the options.

### Manual CSV edits are not picked up

Every command re-reads the tables, so edits should apply immediately. Check that
you edited the path shown by `config show`, saved the file as UTF-8 CSV, and kept
required columns (`question_id` and `job_id`, for example). Invalid statuses raise
an error naming the bad row.

## Packets and tracking

### Packet is generated but the status stays `new`/`answering`

`packet_ready` requires every question to be `approved`, `reused`, or `skipped`.
Resolve pending questions or skip them, then rerun `packet`.

### `A matching company/title was already recorded for season ...`

The duplicate guard found an application with the same normalized company and
title in `[application].season`. If this is genuinely a different opening, pass
`--force`; otherwise update the existing application:

```bash
uv run jobscraper applications update APPLICATION_ID --status interview
```

### Wrong season in application history

Set `[application].season` explicitly (for example `"2026"`). Blank means the
current calendar year. Changing it affects future duplicate checks, not existing
rows.

## Browser autofill

### `Could not launch Chromium`

Install Playwright's browser:

```bash
uv run playwright install chromium
```

or point at a system browser:

```toml
[autofill]
browser_executable = "/usr/bin/chromium"
```

`uv run jobscraper doctor` shows what was detected. On Linux, a snap-packaged
`chromium-browser` can be found via `PATH` but fail to launch in restricted
environments; use Playwright's Chromium or a native Chrome binary instead.

### `Locator.select_option: Timeout ... did not find some options`

The saved answer does not match any option text. Update the answer to the exact
label:

```bash
uv run jobscraper questions set QUESTION_ID --answer "No"
```

Then rerun the dry run to confirm the plan.

### `No matching saved question`

Scan the form first, or create the question manually in `questions.csv` with the
correct `field_ref`, question text, kind, options, and an approved answer:

```bash
uv run jobscraper questions scan JOB_ID --html form.html
uv run jobscraper questions set QUESTION_ID --answer "..."
```

### Fields are listed but skipped as `needs_review`

Approve them (`questions approve QUESTION_ID`) or rerun with `--include-drafts`.

### The browser closes before I can review

Use `--keep-open` and run in an interactive terminal, or drop `--no-keep-open`.
With `--no-keep-open` the browser closes when the command ends; take a
`--screenshot` first if you need a record.

### The form has multiple pages

Autofill does not click "Next". Run it per step with each step's URL and saved
answers, or complete the remaining steps manually in the open browser.

## Tests and development

### `uv run pytest` skips browser tests

The integration tests skip when no Chromium can be launched. Install one or set
`JOBSCRAPER_BROWSER_EXECUTABLE` to a working binary.

### Ruff fails on formatting

```bash
uv run ruff check --fix src tests user/parseEgToSet.py
uv run ruff format src tests user/parseEgToSet.py
```

`./scripts/check.sh` runs lint, format check, and tests together.

### Starting over locally

`init` is non-destructive by default. To reset configuration and tables:

```bash
uv run jobscraper init --force   # existing files are backed up as *.bak
```

Personal CSVs, packets, and descriptions are still not deleted automatically.
Remove them explicitly if you want a clean slate.

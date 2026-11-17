# jobscraper

An assisted, AI-powered job search workflow: collect postings from stable public
sources, filter them deterministically, prepare answers to application questions,
generate a review packet, and fill forms in a browser for **you** to submit.

> **jobscraper never submits an application.** It fills forms and leaves the
> final click to you. It also does not scrape LinkedIn or Indeed listings.

## Why this exists

Applying to many jobs is repetitive, but blindly auto-submitting applications is
risky and low quality. jobscraper keeps a human in the loop:

- **Collect** jobs from public APIs and company boards.
- **Filter** them with transparent include/exclude keywords, not a model.
- **Reuse** answers you have already approved for similar questions.
- **Draft** new answers with an LLM only when needed, then require review.
- **Review** a per-job Markdown packet before applying.
- **Autofill** the form with Playwright and click submit yourself.

Everything is stored in editable CSV/YAML files, not a hidden database.

## Features

- Public source adapters: Greenhouse, Lever, Arbeitnow, RemoteOK, and any static
  page that exposes JSON-LD `JobPosting` data.
- Deterministic keyword filtering with include/exclude lists, `any`/`all` mode,
  and word-aware phrase matching (`senior` does not match `seniority`).
- Reusable answer bank with question-similarity matching and `{company}`,
  `{role}`, and `{name}` placeholders.
- Optional OpenAI-compatible or Ollama drafting. No automatic model downloads.
- Reviewable Markdown application packets.
- Playwright form planning and autofill with no submit action.
- Application tracking with same-season duplicate protection.
- CSV tables that can be edited by hand between commands; extra columns are
  preserved on rewrite.
- `uv`-managed virtual environment, tests, linting, and subfolder docs.

## Requirements

- Python **3.13+** and [uv](https://docs.astral.sh/uv/).
- Optional: Chromium or Chrome for browser autofill. Managed Playwright
  Chromium, or a system `chromium` / `chromium-browser` / `google-chrome`.
- Optional: an OpenAI-compatible endpoint or a local
  [Ollama](https://ollama.com/) server for AI drafting.

No global Python packages are required; everything runs in the project `.venv`.

## Quick start

```bash
uv sync

# Create user/user.toml, user/urls.yaml, a starter resume, .env.local,
# and the four CSV tables. Existing files are left alone.
uv run jobscraper init

# Edit the files that were created:
#   user/user.toml      profile, keywords, paths, LLM and autofill settings
#   user/urls.yaml      which job sources to use
#   user/resume.md      replace with your real resume
#   .env.local          LLM credentials, if you want AI drafting

uv run jobscraper doctor
```

Then run the workflow:

```bash
# 1. Collect and keyword-filter jobs.
uv run jobscraper collect --limit 50

# 2. Inspect what matched.
uv run jobscraper jobs list --status new

# 3. Save the application form as HTML and scan its questions.
uv run jobscraper questions scan JOB_ID --url https://example.com/apply

# 4. Draft answers with the configured LLM (requires a provider).
uv run jobscraper questions answer JOB_ID

# 5. Review answers, then approve them.
uv run jobscraper questions list JOB_ID
uv run jobscraper questions set QUESTION_ID --answer "..."

# 6. Generate a packet and review it.
uv run jobscraper packet JOB_ID

# 7. Fill the real form in a visible browser and submit it yourself.
uv run jobscraper autofill JOB_ID --url https://example.com/apply --fill

# 8. Record the submission.
uv run jobscraper track JOB_ID
```

`questions scan` works on static HTML. For JavaScript-heavy or multi-step forms,
save the rendered page HTML from your browser first and use
`questions scan JOB_ID --html saved-form.html`, or use
`autofill JOB_ID --url ... --save-questions` against the live page.

## CLI reference

Run `uv run jobscraper --help` or `uv run jobscraper COMMAND --help` for the full
option list. All commands accept `--root PATH` (before the command) to point at
a project root other than the current upward search.

| Command | What it does |
| --- | --- |
| `init [--force]` | Create configs, a starter resume, `.env.local`, and empty tables. `--force` backs up and replaces existing files. |
| `doctor [--check-llm]` | Validate config, sources, tables, resume, LLM, and browser. |
| `collect [--source NAME] [--limit N] [--dry-run] [--json]` | Fetch, normalize, filter, and store postings. |
| `filter` | Re-apply keywords to jobs that are not applied. |
| `jobs list [--status S] [--limit N] [--json]` | List stored jobs. |
| `jobs show JOB_ID` | Show one job, its questions, and a description excerpt. |
| `jobs refresh` | Recalculate job statuses from questions and applications. |
| `questions scan JOB_ID (--url U \| --html F) [--ai] [--json]` | Extract form questions. |
| `questions list JOB_ID [--json]` | List a job's questions and answers. |
| `questions answer JOB_ID [--include-existing]` | Draft answers with the LLM. |
| `questions set QUESTION_ID --answer A [--draft] [--notes N]` | Set an answer; approval also updates the bank. |
| `questions approve QUESTION_ID` | Approve the current answer. |
| `questions skip QUESTION_ID` | Mark a question intentionally skipped. |
| `questions bank list [QUERY] [--json]` | Inspect reusable answers. |
| `packet JOB_ID [--out DIR]` | Write a Markdown application packet. |
| `autofill JOB_ID [--url U] [--fill] [--save-questions] [--screenshot F]` | Plan or fill a form; never submits. |
| `track JOB_ID [--status S] [--notes N] [--force]` | Record a submission. |
| `applications list [--json]` | List recorded applications. |
| `applications update APPLICATION_ID [--status S] [--notes N]` | Update application progress. |
| `config show` | Print resolved configuration with secrets masked. |

## Where your data lives

All personal data is under `user/` and is gitignored.

| Path | Contents |
| --- | --- |
| `user/user.toml` | Your profile, keywords, paths, and settings. |
| `user/urls.yaml` | Enabled job sources. |
| `user/extendedTags.yaml` | Extra include keywords merged with `[tags].include`. |
| `user/resume.md` (or `.pdf`/`.txt`) | Resume text for prompts and upload. |
| `user/jobStatusTable.csv` | Discovered jobs and statuses. |
| `user/questions.csv` | Per-job form questions and answers. |
| `user/questionBank.csv` | Reusable approved answers. |
| `user/jobAppliedTable.csv` | Application history. |
| `user/jobDetails/` | Cached plain-text job descriptions. |
| `user/applications/` | Generated application packets. |

Tracked examples (`user/*.example.*`, `.env.example`) are safe to commit.
`user.toml`, the CSVs, secrets, resume, descriptions, and packets are not.

### Status vocabularies

- **Job:** `new`, `filtered_out`, `answering`, `answered`, `packet_ready`,
  `applied`, `skipped`.
- **Question:** `unanswered`, `needs_review`, `approved`, `reused`, `skipped`.
- **Application:** `applied`, `interview`, `rejected`, `offer`, `withdrawn`.
- **Answer kind:** `free_text`, `boolean`, `multiple_choice`, `file`.

Booleans are stored as `true`/`false`; yes/no is accepted on input.
See [docs/configuration.md](docs/configuration.md) for all aliases and columns.

## Configuration summary

Settings live in `user/user.toml` with sections `[general]`, `[tags]`, `[paths]`,
`[llm]`, `[scraping]`, `[matching]`, `[application]`, and `[autofill]`.
Secrets live in `.env.local` (or `.env`), which is loaded first and never
overrides already-set variables.

LLM resolution in `provider = "auto"` mode:

1. An API key is present → OpenAI-compatible endpoint.
2. `OLLAMA_HOST` is set, or the base URL mentions Ollama/port 11434 → Ollama.
3. A non-official base URL and model are set → local OpenAI-compatible server.
4. Otherwise → AI features are disabled and collection/filtering still work.

The official OpenAI endpoint without a key is treated as unavailable. No model
is downloaded automatically. OpenAI-compatible base URLs may be given as a root
or a full endpoint: trailing `/chat/completions`, `/completions`, or `/responses`
suffixes are normalized. This makes OpenRouter's `openrouter/free` router usable;
jobscraper also handles free models that require reasoning or exhaust their
output budget while thinking.

See [docs/configuration.md](docs/configuration.md) for the full reference and
[user/user.example.toml](user/user.example.toml) for a working example.

## Project layout

```
src/jobscraper/
  cli.py          Typer command-line interface
  config.py       root discovery, .env loading, typed user.toml
  models.py       jobs, questions, answers, applications
  browser/        form extraction and assisted autofill
  core/           collection, question workflow, packets, tracking
  llm/            providers, factory, prompt templates
  services/       init, doctor, resume loading
  sources/        adapters, JSON-LD parsing, source config
  storage/        CSV tables and repositories
  utils/          errors, HTTP, matching, text, logging
tests/            offline unit tests plus opt-in browser integration tests
user/             editable configuration and personal data
docs/             user and developer documentation
scripts/          small helper scripts
```

## Development

```bash
uv sync
uv run ruff check src tests user/parseEgToSet.py
uv run ruff format src tests user/parseEgToSet.py
uv run pytest -q
./scripts/check.sh          # lint + format check + tests
```

Browser integration tests use a local fixture and skip when Chromium cannot be
launched. They are marked `integration` but run with the normal suite. To run
them explicitly:

```bash
uv run pytest -m integration -q
```

## Documentation

- [docs/README.md](docs/README.md) — documentation index
- [docs/architecture.md](docs/architecture.md) — module map and data flow
- [docs/configuration.md](docs/configuration.md) — every setting, env var, and CSV column
- [docs/sources.md](docs/sources.md) — supported sources and adding adapters
- [docs/questions.md](docs/questions.md) — question extraction, matching, drafting, approval
- [docs/browser-autofill.md](docs/browser-autofill.md) — autofill behavior and browser setup
- [docs/troubleshooting.md](docs/troubleshooting.md) — common errors and fixes

## Limitations and responsible use

- **Assisted only.** There is no submit click, no login automation, and no
  captcha solving. Review every form before submitting.
- **No LinkedIn/Indeed listing scrapers.** They are fragile, anti-bot heavy, and
  against their terms. Use individual public posting URLs with the generic
  adapter if they expose JSON-LD, or apply manually.
- **Static pages and simple forms.** `questions scan --url` fetches raw HTML;
  JavaScript-rendered forms work through the live `autofill` browser but not the
  static scanner. Shadow DOM, cross-origin iframes, and custom widgets are not
  traversed.
- **Respect source terms and rate limits.** Keep `request_delay_seconds` and
  default limits reasonable. Public APIs can change without notice.
- **AI output can be wrong.** Drafts are untrusted until you review and approve
  them. Never let the model invent credentials, dates, or legal status.
- **Your data stays local.** Prompts are sent only to the provider you configure.
  `.env.local`, CSVs, resumes, and packets are gitignored.

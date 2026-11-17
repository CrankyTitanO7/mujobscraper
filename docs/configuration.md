# Configuration reference

Configuration lives in `user/user.toml`. Personal data and secrets stay out of
git: `user/user.toml`, CSVs, `.env.local`, resumes, descriptions, and packets are
gitignored. Tracked examples end in `.example.*`.

Run `uv run jobscraper config show` to see the fully resolved configuration
(secrets masked) and `uv run jobscraper doctor` to validate it.

## Project root and environment

The project root is resolved in this order:

1. `--root PATH` passed before a CLI command.
2. `JOBSCRAPER_ROOT` environment variable.
3. The nearest parent (including the current directory) containing
   `user/user.toml`.
4. The nearest parent containing `pyproject.toml`.
5. The current directory.

Environment files are loaded from the resolved root:

1. `.env.local` first.
2. `.env` second.
3. Variables already set in the process are never overwritten.

`uv run jobscraper init` copies `.env.example` to `.env.local` if it can, but an
existing `.env.local` is never replaced unless `--force` is passed.

## `user/user.toml`

The example below is the canonical starting point. Extra keys are rejected so
typos fail loudly; unknown keys raise a configuration error naming the file.

```toml
[general]
name = "Big John"
email = "bigjohn@gmail.com"
phone = ""
address = "123 Big John Street, Big John, Connecticut 06515, USA"
current_employment = "Big John Company"
resume = "user/resume.md"

[general.links]
linkedin = "https://www.linkedin.com/in/bigjohn"
github = "https://github.com/bigjohn"

[tags]
include = ["internship", "machine learning"]
disclude = ["senior", "entry level"]
match_mode = "any"

[paths]
urls = "user/urls.yaml"
extendedTags = "user/extendedTags.yaml"
jobStatusTable = "user/jobStatusTable.csv"
jobAppliedTable = "user/jobAppliedTable.csv"
questionsTable = "user/questions.csv"
questionBankTable = "user/questionBank.csv"
jobDetailsDir = "user/jobDetails"
applicationsDir = "user/applications"

[llm]
provider = "auto"
base_url = ""
model = ""
api_key_env = "JOBSCRAPER_LLM_API_KEY"
temperature = 0.2
timeout = 120
max_resume_chars = 12000
adapt_reused_answers = true
refine_extraction = true

[scraping]
limit = 100
timeout = 30
retries = 2
request_delay_seconds = 0.5
user_agent = "jobscraper/0.1"

[matching]
similarity_threshold = 0.82

[application]
season = "2026"
require_approval = true
duplicate_guard = true

[autofill]
headless = false
keep_open = true
include_drafts = false
timeout_ms = 30000
browser_executable = ""
```

### `[general]`

| Key | Default | Purpose |
| --- | --- | --- |
| `name` | empty | Used in prompts and `{name}` answer placeholders. |
| `email` | empty | Profile context for answers. |
| `phone` | empty | Profile context for answers. |
| `address` | empty | Profile context for answers. |
| `current_employment` | empty | Profile context for answers. |
| `resume` | `user/resume.md` | Resume path (PDF, Markdown, or text). |
| `links` | `{}` | Free-form label/URL pairs included in prompts. |

`load_resume` accepts `.pdf` (via `pypdf`), `.md`, `.markdown`, `.txt`, or no
extension. Reading is truncated to `[llm].max_resume_chars`.

### `[tags]`

| Key | Default | Purpose |
| --- | --- | --- |
| `include` | `[]` | Terms that keep a job. Empty means "allow everything". |
| `disclude` | `[]` | Terms that reject a job. Exclusion always wins. |
| `match_mode` | `any` | `any`: at least one include term; `all`: every include term. |

Matching is case-insensitive, phrase-aware, and respects word edges. A TOML
list or a comma-separated string is accepted for `include` and `disclude`.
Keywords are matched against title, company, location, job type, field, tags,
and the cached description.

`user/extendedTags.yaml` adds more include terms. Both shapes are accepted:

```yaml
extendedTags:
  - remote
  - new grad
```

or a plain YAML list:

```yaml
- remote
- new grad
```

Extended tags are merged into includes; they never become exclusions.

### `[paths]`

All paths are relative to the project root unless absolute. `init` creates the
configured tables and directories.

Aliases are accepted with the camelCase names shown in the example
(`extendedTags`, `jobStatusTable`, etc.).

### `[llm]`

| Key | Default | Purpose |
| --- | --- | --- |
| `provider` | `auto` | `auto`, `openai`, `ollama`, or `none`. |
| `base_url` | empty | Provider base URL; see resolution below. |
| `model` | empty | Model name. Required when AI is enabled. |
| `api_key_env` | `JOBSCRAPER_LLM_API_KEY` | Environment variable checked first for a key. |
| `temperature` | `0.2` | Drafting temperature. |
| `timeout` | `120` | Request timeout in seconds. |
| `max_resume_chars` | `12000` | Resume excerpt limit in prompts. |
| `adapt_reused_answers` | `true` | Let the LLM adapt a reused bank answer (marked `needs_review`). |
| `refine_extraction` | `true` | Global switch for `questions scan --ai`; `false` disables it even when the flag is passed. |

`provider = "auto"` resolves as follows:

1. A key from `api_key_env`, `JOBSCRAPER_LLM_API_KEY`, or `OPENAI_API_KEY` →
   OpenAI-compatible.
2. `OLLAMA_HOST` is set, or the base URL contains `ollama` / `11434` → Ollama.
3. A non-official base URL plus a model → a local OpenAI-compatible server.
4. Anything else → AI disabled. The official `api.openai.com` endpoint without
   a key is always treated as unavailable.

No model is downloaded automatically, and collection/filtering never requires
the LLM.

#### OpenAI-compatible endpoints and OpenRouter

`base_url` may be a provider root or a full endpoint. A trailing
`/chat/completions`, `/completions`, or `/responses` is stripped before the
client appends `/chat/completions`, so both forms work:

```dotenv
JOBSCRAPER_LLM_BASE_URL=https://openrouter.ai/api/v1
# or a full endpoint such as https://openrouter.ai/api/v1/responses
JOBSCRAPER_LLM_MODEL=openrouter/free
JOBSCRAPER_LLM_API_KEY=sk-or-...
```

`config show` and `doctor` display the normalized base URL.

The `openrouter/free` router may select reasoning models. jobscraper asks
OpenRouter to disable reasoning so the output budget is spent on the answer. If
the selected model requires reasoning, the request is retried without that flag
and with a larger token budget. If drafting still fails, choose a specific
non-reasoning free model from OpenRouter's model list.

### `[scraping]`

| Key | Default | Purpose |
| --- | --- | --- |
| `limit` | `100` | Maximum postings inspected per run (overridable with `--limit`). |
| `timeout` | `30` | HTTP timeout in seconds. |
| `retries` | `2` | Retries for transport errors, `429`, and `5xx` responses. |
| `request_delay_seconds` | `0.5` | Delay between requests inside a multi-request adapter. |
| `user_agent` | `jobscraper/0.1` | HTTP User-Agent. |

### `[matching]`

`similarity_threshold` (default `0.82`, range 0–1) is the minimum
question-similarity score for automatically reusing a bank answer. Matching also
requires compatible answer kinds and an approved, non-empty bank answer.
Job type and field matches add a small bonus. See
[questions.md](questions.md).

### `[application]`

| Key | Default | Purpose |
| --- | --- | --- |
| `season` | current year | Hiring cycle used for duplicate protection. |
| `require_approval` | `true` | Safety policy flag. This build never autofills unanswered or unapproved text unless `--include-drafts` is explicitly passed; setting this to `false` does not enable auto-approval. |
| `duplicate_guard` | `true` | Reject a second application with the same normalized company/title in the same season. |

### `[autofill]`

| Key | Default | Purpose |
| --- | --- | --- |
| `headless` | `false` | Show the browser by default. |
| `keep_open` | `true` | In an interactive terminal, wait for Enter before closing after `--fill`. |
| `include_drafts` | `false` | Allow `needs_review` answers. CLI `--include-drafts` overrides. |
| `timeout_ms` | `30000` | Navigation and locator timeout. |
| `browser_executable` | empty | Absolute path to a system Chrome/Chromium. Empty uses managed Playwright Chromium, then system browsers. |

## Environment variables

| Variable | Purpose |
| --- | --- |
| `JOBSCRAPER_ROOT` | Force a project root. |
| `JOBSCRAPER_LLM_PROVIDER` | Override `[llm].provider`. |
| `JOBSCRAPER_LLM_BASE_URL` | Override `[llm].base_url`. |
| `JOBSCRAPER_LLM_MODEL` | Override `[llm].model`. |
| `JOBSCRAPER_LLM_API_KEY` | API key (also the default `api_key_env`). |
| `OPENAI_API_KEY` | Fallback API key. |
| `OLLAMA_HOST` | Ollama base URL, e.g. `http://localhost:11434`. |
| `JOBSCRAPER_BROWSER_EXECUTABLE` | Override `[autofill].browser_executable`. |

Secrets are never written by jobscraper. `config show` masks a present key as
`***`.

## CSV tables

All tables are UTF-8 CSV. A BOM is tolerated. Lists inside a cell are separated
by semicolons (`; `). Rows where every cell is blank are ignored. Extra columns
you add by hand are preserved when jobscraper rewrites the table. Writes are
atomic and files are created with restrictive permissions where the OS allows.

### `user/jobStatusTable.csv`

| Column | Notes |
| --- | --- |
| `job_id` | Deterministic ID derived from source plus source ID/URL/company/title/location. Required. |
| `status` | Job status. Required. |
| `title` | Job title. Required. |
| `company` | Company. Required. |
| `location`, `job_type`, `field` | Normalized metadata. |
| `source`, `source_id` | Adapter name and provider ID. |
| `url`, `apply_url` | Posting and application links. |
| `tags`, `include_matches`, `exclude_matches` | Semicolon lists. |
| `posted_at`, `first_seen`, `last_seen`, `applied_at` | ISO-8601 timestamps. |
| `notes` | Free text. |
| `description_path` | Relative path under `user/jobDetails/`. |
| `packet_path` | Relative path to the generated packet. |

### `user/questions.csv`

| Column | Notes |
| --- | --- |
| `question_id` | Deterministic; required. |
| `job_id` | Owning job; required. |
| `field_ref` | Form control `name`, `id`, or a stable placeholder. |
| `question` | Human-readable label. |
| `normalized` | Normalized label used for matching. |
| `kind` | `free_text`, `boolean`, `multiple_choice`, `file`. |
| `options` | Semicolon list for choice questions. |
| `answer` | Current answer text. |
| `status` | Question status. |
| `answer_id` | Bank answer used or created. |
| `confidence` | Similarity score when reused. |
| `source` | `html`, `url`, `browser`, or `ai`. |
| `created_at`, `updated_at` | ISO-8601 timestamps. |
| `notes` | Warnings, e.g. "AI answer did not match the form options". |

### `user/questionBank.csv`

| Column | Notes |
| --- | --- |
| `answer_id` | Deterministic from normalized question plus kind. |
| `question`, `normalized` | Original and normalized question text. |
| `kind` | Answer kind. |
| `answer` | Reusable answer; supports `{company}`, `{role}`, `{name}`. |
| `status` | `approved`, `draft`, or `archived`. |
| `category`, `job_type`, `job_field` | Optional matching hints. |
| `times_used`, `last_used` | Usage counters. |
| `created_at`, `updated_at`, `notes` | Metadata. |

### `user/jobAppliedTable.csv`

| Column | Notes |
| --- | --- |
| `application_id` | Deterministic; required. |
| `job_id` | Applied job. |
| `company`, `title` | Copied from the job for readable history. |
| `season` | Hiring cycle used by the duplicate guard. |
| `status` | Application status. |
| `applied_at`, `updated_at` | ISO-8601 timestamps. |
| `resume`, `packet_path` | Paths used for the submission. |
| `notes` | Free text; new notes are appended on separate lines. |

## Status and kind values

| Field | Values | Accepted aliases |
| --- | --- | --- |
| Job status | `new`, `filtered_out`, `answering`, `answered`, `packet_ready`, `applied`, `skipped` | `not started`, `not_started`, `filtered`, `filtered out`, `packet`, `packet ready`, `submitted` |
| Question status | `unanswered`, `needs_review`, `approved`, `reused`, `skipped` | `pending`, `draft`, `answered` |
| Answer kind | `free_text`, `boolean`, `multiple_choice`, `file` | `text`, `bool`, `yes_no`, `choice`, `select`, `upload` |
| Bank status | `approved`, `draft`, `archived` | none |
| Application status | `applied`, `interview`, `rejected`, `offer`, `withdrawn` | none |

Values are case-insensitive and accept hyphens in place of underscores.

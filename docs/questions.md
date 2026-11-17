# Questions, answers, and the answer bank

The question workflow is deliberately conservative: extraction and matching are
local and deterministic, the LLM only drafts, and nothing is used for autofill
until it is approved (or reused from an approved bank answer).

## Lifecycle

```
form HTML ──► extract fields ──► questions.csv ──► bank match ──► reused
                                                   │
                                                   └─ no match ──► unanswered
                                                                       │
                                                        LLM draft ─────┤
                                                                       ▼
                                                                  needs_review
                                                                       │
                                                     questions set/approve
                                                                       ▼
                                                                   approved
                                                                       │
                                                              questionBank.csv
```

| Status | Meaning | Autofilled by default? |
| --- | --- | --- |
| `unanswered` | No usable answer. | No |
| `needs_review` | Draft or adapted answer awaiting a human. | No |
| `approved` | Explicitly approved; copied to the bank. | Yes |
| `reused` | Taken from an approved bank answer without adaptation. | Yes |
| `skipped` | Deliberately ignored. | No |

`--include-drafts` (CLI) or `[autofill].include_drafts = true` allows
`needs_review` answers to be filled.

## Scanning a form

```bash
# Static HTML fetched over HTTP
uv run jobscraper questions scan JOB_ID --url https://example.com/apply

# A page you saved from your browser (works for JS-rendered forms)
uv run jobscraper questions scan JOB_ID --html saved-form.html

# Ask the LLM to clean up labels and drop non-questions
uv run jobscraper questions scan JOB_ID --url ... --ai

# Machine-readable output
uv run jobscraper questions scan JOB_ID --html saved-form.html --json
```

The heuristic parser (`browser/forms.py`) handles:

- `input` types except hidden, submit, button, reset, image, and search.
- `textarea` and `select`.
- Radio groups sharing a `name`, grouped into one boolean or choice question.
- Checkbox groups; a single checkbox is a boolean, multiple checkboxes are a
  multiple-choice group.
- Labels from `aria-label`, `aria-labelledby`, `<label for=...>`, a wrapping
  `<label>`, placeholder, fieldset `<legend>`, or nearby text.
- Select options, excluding placeholder entries such as "Select…" and
  "Choose…".

With `--ai`, the extracted fields are sent to the LLM, which may rewrite labels,
classify kinds, and drop navigation/search fields. Results are matched back by
`field_ref`; unknown refs are ignored. If the LLM fails or returns invalid JSON,
the heuristic fields are kept. `[llm].refine_extraction = false` disables this
even when `--ai` is passed.

File inputs whose label mentions resume/CV are marked `file`. If the configured
resume exists, they are approved automatically with the resume path as the
answer; otherwise they stay unanswered with a note.

## Matching bank answers

`best_bank_match` considers only bank answers that are:

- `status = approved`,
- non-empty,
- kind-compatible with the question.

Kind compatibility:

| Question kind | Compatible bank kinds |
| --- | --- |
| `free_text` | `free_text`, `boolean`, `multiple_choice` |
| `boolean` | `boolean` only |
| `multiple_choice` | `multiple_choice`, `free_text` |
| `file` | never reused |

Similarity combines normalized string similarity with token overlap. Job-type
and job-field matches add a small bonus. The score must reach
`[matching].similarity_threshold` (default `0.82`).

A reused answer is rendered with placeholders:

- `{company}` → job company
- `{role}` → job title
- `{name}` → `[general].name`

If `[llm].adapt_reused_answers = true` and an LLM is available, the reused text
is passed back through the model with instructions to adapt names and grammar
without changing facts. The question then becomes `needs_review` instead of
`reused`. Bank usage counters (`times_used`, `last_used`) are updated either way.

## Drafting answers

```bash
uv run jobscraper questions answer JOB_ID
uv run jobscraper questions answer JOB_ID --include-existing
```

Drafting requires a configured provider. For each `unanswered` or
`needs_review` question (file questions excluded):

1. Build a prompt containing your profile, the job, the question, any existing
   bank reference, and a resume excerpt.
2. Ask for a direct answer, or `[[UNKNOWN]]` when the facts are insufficient.
3. Validate the shape:
   - boolean answers normalize to `true`/`false`;
   - multiple-choice answers must match a form option exactly
     (case/punctuation-insensitive);
   - free text is kept as written.
4. Save drafts as `needs_review`. If the model returns `[[UNKNOWN]]`, the
   question stays `unanswered` with a note.

Drafts never auto-approve and never auto-fill. `--include-existing` redrafts
`needs_review` questions; it does not overwrite `approved` or `reused` answers.

## Reviewing and approving

```bash
# List all questions for one job
uv run jobscraper questions list JOB_ID

# Set an answer and approve it (also updates the bank)
uv run jobscraper questions set QUESTION_ID --answer "..."

# Save a draft without approving
uv run jobscraper questions set QUESTION_ID --answer "..." --draft

# Approve whatever answer is already on the question
uv run jobscraper questions approve QUESTION_ID

# Intentionally skip a question
uv run jobscraper questions skip QUESTION_ID
```

Validation on `set`:

- Boolean questions accept `true`, `false`, `yes`, `no`, `y`, `n`, `1`, `0`,
  `authorized`, `not authorized`, and store canonical `true`/`false`.
- Multiple-choice questions must match one of the stored options.
- Empty answers are rejected.
- Approval upserts a bank row: the linked bank answer is updated, else an exact
  normalized match is updated, else a new `approved` row is created. The bank row
  records category, job type, and job field for future matching.

## The answer bank

```bash
uv run jobscraper questions bank list
uv run jobscraper questions bank list python
uv run jobscraper questions bank list --json
```

`user/questionBank.csv` is a normal editable CSV. You can add rows by hand as
long as they have an `answer_id` (any stable unique string), `status = approved`,
a non-empty `answer`, and a compatible `kind`. Editing the answer text in place
is supported and is picked up by the next command.

Use placeholders to avoid stale company names:

```csv
answer_id,question,normalized,kind,answer,status,...
a_example,Why this company?,why this company,free_text,"I want to join {company} because ...",approved,...
```

Bank statuses are `approved`, `draft`, and `archived`. Only `approved` rows are
reused. Remove or archive rows you no longer want offered.

## Status side effects

After scanning, drafting, setting, approving, or skipping a question,
`refresh_statuses` runs for that job:

- any pending question → `answering`
- all questions `approved`, `reused`, or `skipped` → `answered`
- an application row always wins → `applied`

`uv run jobscraper jobs refresh` applies the same logic to every job, which is
useful after manual CSV edits.

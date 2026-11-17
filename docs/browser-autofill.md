# Browser autofill

Autofill opens an application form, fills answers you have already prepared, and
leaves the final submission to you. **There is no submit click in the code.**

## Safety model

- `autofill` without `--fill` is a dry run: it opens the page, builds a plan, and
  reports what it would do.
- `--fill` populates fields but never presses submit, never navigates away, and
  never accepts terms on your behalf.
- Only `approved` and `reused` question answers are used by default. Drafts need
  `--include-drafts`.
- The browser is headful by default and, in an interactive terminal with
  `keep_open`, waits for Enter before closing.
- Form values are filled from your local tables. The browser does not send data
  anywhere except the application page you opened.

Always review the filled form and submit it yourself.

## Browser setup

Playwright is installed as a Python dependency, but its managed Chromium is a
separate download:

```bash
uv run playwright install chromium
```

jobscraper tries these in order:

1. `[autofill].browser_executable` or `JOBSCRAPER_BROWSER_EXECUTABLE`, if set.
2. Playwright's managed Chromium.
3. A system browser found on `PATH`: `chromium`, `chromium-browser`,
   `google-chrome`, `chrome`.

On many Linux distributions `chromium-browser` is already present, so autofill
works without the Playwright download. `uv run jobscraper doctor` reports which
browser it found.

## Planning and filling

```bash
# Dry run: show the plan
uv run jobscraper autofill JOB_ID --url https://example.com/apply

# Fill the form and leave it open for review
uv run jobscraper autofill JOB_ID --url https://example.com/apply --fill

# Fill, save a screenshot, and close without waiting
uv run jobscraper autofill JOB_ID --url ... --fill --no-keep-open \
  --screenshot /tmp/application.png

# Scan the live page into questions.csv at the same time
uv run jobscraper autofill JOB_ID --url ... --save-questions --fill

# Allow needs_review drafts
uv run jobscraper autofill JOB_ID --url ... --fill --include-drafts
```

If `--url` is omitted, the job's `apply_url` or `url` is used. Headless mode is
available for scripted checks (`--headless`) but is not recommended for real
applications.

## How answers are matched

1. A saved question with the same `field_ref` (control `name` or `id`) wins.
2. Otherwise, the best label similarity must reach `0.62`.
3. Only usable statuses are selected, and the answer must be non-empty.
4. The field kind determines the action:

| Action | Used for | Behavior |
| --- | --- | --- |
| `fill` | text inputs, textareas | `locator.fill(answer)` |
| `select` | `<select>` | Selects by the matching option label |
| `check` | radio/checkbox groups | Checks the matching option(s) |
| `upload` | `input[type=file]` | Uploads the saved file path or resume |
| `skip` | everything else | Reports a reason |

Selects and choices are matched case- and punctuation-insensitively. Boolean
selects with Yes/No options map `true`/`false` to the corresponding option.
Checkbox groups with multiple options are treated as multiple choice; a single
checkbox is a boolean and is checked only when the answer is truthy.

Resume uploads: a `file` question uses its saved answer if that file exists;
otherwise the configured resume is used. A field whose label mentions resume,
CV, or curriculum vitae is treated as a resume upload even if it was not scanned
as a file question.

## What gets skipped, and why

The plan reports one of:

- `No matching saved question` — scan the form or add a question manually.
- `Answer status is unanswered` / `needs_review` — answer/approve it, or pass
  `--include-drafts` for drafts.
- `Answer does not match a select option` — edit the answer to the exact option
  text.
- `Answer does not match an option` — same, for radio/checkbox groups.
- `Resume file is not available` / `No resume file` — set `[general].resume` or
  the file question's answer to an existing path.
- `Fill failed: ...` — usually a timeout or a control that moved; see
  [troubleshooting.md](troubleshooting.md).

## Supported forms

Works well:

- Standard HTML forms with visible `input`, `textarea`, and `select` controls.
- Labels via `label[for]`, wrapping labels, `aria-label`, `aria-labelledby`, or
  placeholders.
- Radio groups and checkbox groups with a shared `name`.
- Resume uploads.
- Single-page forms with a normal URL.

Not supported:

- Clicking submit (by design).
- Logins, captchas, MFA, or bot challenges.
- Shadow DOM, cross-origin iframes, and custom combobox/date widgets.
- Multi-step wizards that render new controls after a "Next" click. Autofill one
  step URL at a time, or fill the remaining steps manually.
- JavaScript-heavy forms in `questions scan --url`; use `--html` with saved
  rendered HTML, or `autofill --save-questions`.

## Review checklist

1. Confirm the job and company are correct.
2. Resolve every `unanswered` and `needs_review` question.
3. Generate and read the packet (`uv run jobscraper packet JOB_ID`).
4. Run autofill and inspect every field, especially booleans, salary, and legal
   questions.
5. Attach the resume and any extra documents.
6. Click submit yourself.
7. Record it: `uv run jobscraper track JOB_ID`.

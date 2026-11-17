# `browser`

Form extraction and assisted autofill. Submission is intentionally absent from
this package.

| Module | Purpose |
| --- | --- |
| `forms.py` | Parse HTML into `FormField` records: label, kind, options, DOM indices, required flag. |
| `autofill.py` | Match questions to fields, build a `FillPlan`, optionally fill with Playwright, capture screenshots. |

## `forms.py`

- Uses BeautifulSoup (no browser required), so it works on saved HTML and live
  `page.content()`.
- Joins radio groups by `name`; joins checkbox groups by `name`.
- Resolves labels from `aria-label`, `aria-labelledby`, `label[for]`, wrapping
  labels, placeholders, `<legend>`, or nearby text.
- Classifies booleans, multiple choice, free text, and file uploads.
- Records `dom_index`/`control_indices` so the filler can address controls with
  `page.locator("input, textarea, select").nth(i)` instead of fragile selectors.

## `autofill.py`

- `find_question_for_field` prefers an exact `field_ref` match, then falls back
  to label similarity (`>= 0.62`).
- `build_fill_plan` is deterministic and side-effect free. It only uses approved
  or reused answers unless drafts are explicitly allowed.
- `autofill_job` launches a browser (managed Chromium, then system Chromium or
  Chrome), navigates, optionally scans questions, builds the plan, and fills when
  `fill=True`.
- It never clicks submit. With `keep_open` in a TTY it waits for Enter before
  closing so you can review.
- `_apply_plan` isolates failures per field and records the reason on the plan.
- Launch failures are normalized to `BrowserError` with installation guidance.

See [docs/browser-autofill.md](../../../docs/browser-autofill.md) for behavior,
supported controls, and setup.

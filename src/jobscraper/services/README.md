# `services`

Operational helpers used by the CLI: project initialization, diagnostics, and
resume loading.

| Module | Public API | Purpose |
| --- | --- | --- |
| `init.py` | `initialize_project(root, force=False)` | Copy tracked examples into user files, create directories and empty CSV tables. |
| `doctor.py` | `run_doctor(config, check_llm=False)`, `Check` | Validate config, sources, tables, resume, LLM, and browser detection. |
| `resume.py` | `load_resume(config, required=False)`, `resume_path` | Read Markdown/text/PDF resumes with truncation. |

## Initialization

`init` is non-destructive by default:

- Existing targets are skipped.
- Missing templates only fail init when the target actually needs to be created
  (`.env.local` is optional).
- `force=True` copies an existing target to `*.bak` before replacing it.
- Tables are created from the resolved configuration, so custom `[paths]` work.
- No secret values are invented; `.env.local` is copied from `.env.example`.

## Doctor

Checks are returned as `Check(name, ok, detail, warning=False)`. Warnings do not
fail the command; hard failures exit non-zero. `check_llm` sends a tiny request
to the configured provider. Browser detection checks the configured executable,
then `PATH` names, then the Playwright cache.

## Resume loading

- `.pdf` uses `pypdf` and extracts text page by page.
- `.md`, `.markdown`, `.txt`, or no extension is read as UTF-8.
- Missing resumes are optional unless `required=True`.
- Text is truncated to `[llm].max_resume_chars`.
- Unsupported extensions raise `ConfigError` with supported formats.

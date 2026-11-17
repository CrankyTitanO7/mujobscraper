# `src/jobscraper`

Main package for the assisted job workflow. The CLI is the supported entry
point; modules are organized by responsibility and import only through their
public interfaces.

## Entry points

| File | Purpose |
| --- | --- |
| `cli.py` | Typer application and console-script target (`jobscraper.cli:main`). |
| `__main__.py` | Enables `python -m jobscraper`. |
| `config.py` | Root discovery, `.env` loading, typed `user.toml`, path resolution. |
| `models.py` | Dataclasses and enums shared across layers. |

## Packages

- [`core/`](core/README.md) — collection, questions, packets, tracking, statuses.
- [`sources/`](sources/README.md) — job-board adapters and source configuration.
- [`storage/`](storage/README.md) — atomic CSV tables and repositories.
- [`llm/`](llm/README.md) — OpenAI-compatible and Ollama providers, prompts.
- [`browser/`](browser/README.md) — form extraction and assisted autofill.
- [`services/`](services/README.md) — initialization, diagnostics, resume loading.
- [`utils/`](utils/README.md) — errors, HTTP, text, matching, logging.

## Conventions

- Expected failures raise subclasses of `utils.errors.JobscraperError`; the CLI
  prints them without a traceback.
- User-visible data is plain CSV/YAML/Markdown, re-read on every command.
- Writes to tables and files are atomic (temp file in the same directory, then
  replace).
- Network and LLM dependencies are injectable for offline tests.
- No module submits an application or downloads a model.
- Keep modules free of CLI concerns; formatting belongs in `cli.py`.

## Adding functionality

1. Put domain logic in `core/` or the relevant package, not in `cli.py`.
2. Add typed configuration to `config.py` or `sources/config.py` and update
   `user/user.example.toml` / `user/urls.example.yaml`.
3. Add offline tests under `tests/`.
4. Update the relevant README in this tree and the user docs in `docs/`.

# jobscraper documentation

These documents go deeper than the root [README](../README.md). Start with the
README quick start, then use the page that matches your task.

## Guides

| Document | Audience | Contents |
| --- | --- | --- |
| [architecture.md](architecture.md) | contributors | Module map, data flow, status transitions, design principles. |
| [configuration.md](configuration.md) | users | Every `user.toml` setting, environment variable, CSV table, and status value. |
| [sources.md](sources.md) | users, contributors | `urls.yaml`, supported adapters, JSON-LD extraction, adding a source. |
| [questions.md](questions.md) | users | Scanning forms, answer reuse, AI drafting, approval, and the answer bank. |
| [browser-autofill.md](browser-autofill.md) | users | Autofill safety model, browser setup, options, and supported controls. |
| [troubleshooting.md](troubleshooting.md) | users | Common errors with concrete fixes. |

## Subfolder documentation

Each package has a short README describing its responsibility and public entry
points:

- [src/jobscraper](../src/jobscraper/README.md)
- [core](../src/jobscraper/core/README.md)
- [sources](../src/jobscraper/sources/README.md)
- [storage](../src/jobscraper/storage/README.md)
- [llm](../src/jobscraper/llm/README.md)
- [browser](../src/jobscraper/browser/README.md)
- [services](../src/jobscraper/services/README.md)
- [utils](../src/jobscraper/utils/README.md)
- [tests](../tests/README.md)
- [user](../user/README.md)
- [scripts](../scripts/README.md)

## Conventions used in these docs

- Commands assume you are in the repository root and use `uv run`.
- `JOB_ID`, `QUESTION_ID`, and `APPLICATION_ID` stand for values from the CSV
  tables or CLI output.
- "LLM" means the optional OpenAI-compatible or Ollama provider configured in
  `.env.local`; it is never required for collection or filtering.
- Paths are relative to the project root unless stated otherwise.

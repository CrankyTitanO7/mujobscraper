# Tests

The suite is offline by default except for the browser integration tests, which
use a local fixture page and skip when Chromium cannot be launched.

```bash
uv run pytest -q
uv run pytest -m integration -q        # browser tests only
uv run pytest tests/test_questions.py -q
uv run pytest -k matching -q
```

## Coverage by file

| File | Focus |
| --- | --- |
| `test_config.py` | Config loading, path resolution, root discovery, source YAML shapes. |
| `test_matching.py` | Word-boundary keywords, include/exclude modes, question similarity, placeholders. |
| `test_storage.py` | CSV round trips, BOM handling, custom columns, repository parsing, duplicate lookup. |
| `test_sources.py` | Each adapter via `httpx.MockTransport`, JSON-LD extraction, registry wiring. |
| `test_collection.py` | Deduplication, filtering, dry runs, status preservation, limits, re-filtering. |
| `test_questions.py` | Field extraction, bank reuse, drafting, validation, approval, status refresh. |
| `test_applications.py` | Packet rendering/status, tracking, duplicate guard, application updates. |
| `test_llm.py` | OpenAI/Ollama request shapes, provider resolution, prompts, JSON parsing. |
| `test_resume.py` | Markdown/text/PDF loading, optional and unsupported resumes, truncation. |
| `test_browser.py` | Field extraction, fill planning, and Playwright fill/no-submit integration. |
| `test_cli.py` | Version, init, config, jobs, track, doctor, questions, help. |

## Fixtures and fakes

- `conftest.py` builds a temporary project root with the example config, empty
  tables, a resume, and a test URL config.
- `make_job(config, ...)` inserts a job and its description file.
- `FakeProvider` is a scriptable LLM that records prompts.
- `tests/fixtures/sample_form.html` exercises text, email, tel, file, radio,
  select, textarea, and checkbox controls.
- HTTP tests inject `httpx.MockTransport`; no network calls are made.
- LLM tests use `MockTransport` or `FakeProvider`; no keys or servers needed.

## Conventions

- Keep tests deterministic and offline unless marked `integration`.
- Assert behavior, not implementation details, where practical.
- Add a regression test for every bug fix.
- Use the temporary `config` fixture instead of touching the real `user/` files.
- Integration tests are decorated with `@pytest.mark.integration` and skip
  cleanly when a browser is unavailable.

# `sources`

Job-source adapters and their configuration. Every adapter implements
`JobSource.fetch(client) -> list[JobPosting]` and returns normalized postings.

| Module | Purpose |
| --- | --- |
| `base.py` | `JobSource` abstract base class. |
| `config.py` | Pydantic models for `user/urls.yaml`, legacy list/key normalization. |
| `registry.py` | `build_sources` instantiates enabled adapters with request delays. |
| `greenhouse.py` | Public Greenhouse board API. |
| `lever.py` | Public Lever postings API. |
| `arbeitnow.py` | Arbeitnow public API with pagination and search filtering. |
| `remoteok.py` | RemoteOK public feed with tag filtering. |
| `generic.py` | Static HTML pages using JSON-LD or OpenGraph metadata. |
| `jsonld.py` | JSON-LD `JobPosting` extraction and metadata fallback. |
| `common.py` | Small parsing helpers (lists, names, epochs, descriptions, search). |
| `metadata.py` | `job_type`/`field` heuristics and tag merging. |

## Configuration

`SourcesConfig` rejects unknown keys. `arbeitnow` and `remoteok` default to
disabled when their sections are omitted; the example file enables them
explicitly. `greenhouse`, `lever`, and `generic` also require at least one
board/company/URL to run.

See [docs/sources.md](../../../docs/sources.md) for the YAML reference and the
JSON-LD mapping.

## Adding an adapter

1. Subclass `JobSource` and set `name`.
2. Parse provider data into `JobPosting`, using `common.py`/`metadata.py`.
3. Add a config section in `config.py` and a branch in `registry.py`.
4. Test with `httpx.MockTransport`; no live network in unit tests.
5. Document the new source and update `user/urls.example.yaml`.

Adapters must not require credentials, must respect rate limits, and should
isolate per-board/per-company failures so one bad token does not abort a run.

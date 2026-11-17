# `llm`

Optional model access for drafting answers and refining extracted questions.

| Module | Purpose |
| --- | --- |
| `base.py` | `LLMProvider` protocol: `complete(system, prompt, temperature=..., max_tokens=...)`. |
| `openai.py` | `OpenAICompatibleProvider` for OpenAI, LM Studio, vLLM, and similar servers. |
| `ollama.py` | `OllamaProvider` for a local Ollama daemon. |
| `factory.py` | `resolve_settings` and `build_provider` implement provider selection. |
| `prompts.py` | Prompt templates, the `[[UNKNOWN]]` marker, and tolerant JSON-array parsing. |

## Resolution

`provider = "auto"` chooses:

1. OpenAI-compatible when an API key exists.
2. Ollama when `OLLAMA_HOST` is set or the base URL mentions Ollama/port 11434.
3. A non-official base URL plus model → local OpenAI-compatible server.
4. Otherwise `none`, and AI features raise `LLMUnavailableError` with setup
   instructions.

The official `api.openai.com` endpoint without a key is treated as unavailable.
Keys come from `[llm].api_key_env`, then `JOBSCRAPER_LLM_API_KEY`, then
`OPENAI_API_KEY`.

## Design notes

- Providers implement a single blocking `complete` method; callers own prompts
  and validation.
- Requests use the shared `HttpClient` with retries disabled for LLM calls.
  The provider itself retries when a response is truncated before producing
  text, doubling the token budget up to three attempts.
- OpenAI-compatible base URLs may include a full endpoint suffix; known
  `/chat/completions`, `/completions`, and `/responses` suffixes are normalized.
- OpenRouter requests ask to disable reasoning by default. If the selected free
  model requires reasoning, the request is retried without that flag.
- No streaming, no tool calls, and no automatic model downloads.
- The factory accepts an injected `httpx` transport for offline tests.
- `utils/errors.LLMError` wraps transport, HTTP, and malformed-response failures.

## Prompt safety

The system prompt instructs the model to use only supplied facts and to return
`[[UNKNOWN]]` when it cannot answer responsibly. Drafts are always stored as
`needs_review`; the model never approves or submits anything.

See [docs/configuration.md](../../../docs/configuration.md) for settings and
[docs/questions.md](../../../docs/questions.md) for the workflow.

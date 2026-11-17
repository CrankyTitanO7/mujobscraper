"""OpenAI-compatible chat-completions provider."""

from __future__ import annotations

import httpx

from ..utils.errors import LLMError
from ..utils.http import HttpClient

DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MAX_ATTEMPTS = 3
_MAX_RETRY_TOKENS = 4096


class OpenAICompatibleProvider:
    """Works with OpenAI, LM Studio, vLLM, and other compatible servers."""

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_openai_base_url(base_url)
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Return the assistant text, retrying when reasoning exhausts the budget.

        Free OpenRouter routers may select reasoning models that spend the
        entire ``max_tokens`` budget thinking and return ``content: null`` with
        ``finish_reason: "length"``. OpenRouter is asked to disable reasoning;
        if a model still truncates, retry with a larger budget.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        budget = max(1, max_tokens)
        disable_reasoning = "openrouter.ai" in self.base_url.casefold()
        last_detail = ""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            payload = self._payload(
                system,
                prompt,
                temperature=temperature,
                max_tokens=budget,
                disable_reasoning=disable_reasoning,
            )
            try:
                data = self._post(payload, headers)
            except LLMError as exc:
                if disable_reasoning and _is_reasoning_mandatory_error(exc):
                    # Some free models require reasoning and reject disabling
                    # it. Retry without the parameter and with room to think.
                    disable_reasoning = False
                    budget = _retry_token_budget(budget)
                    continue
                raise
            try:
                choice = data["choices"][0]
                message = choice["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError(
                    f"Unexpected chat-completions response from {self.base_url}"
                ) from exc

            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, str) and not content.strip():
                finish = choice.get("finish_reason", "")
                if not finish or finish != "length":
                    return ""
            finish = choice.get("finish_reason", "")
            reasoning = message.get("reasoning") if isinstance(message, dict) else None
            tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
            last_detail = f" (finish_reason={finish})" if finish else ""

            can_retry = attempt < _MAX_ATTEMPTS and not tool_calls
            if can_retry:
                next_budget = _retry_token_budget(budget)
                if next_budget > budget:
                    budget = next_budget
                    continue

            hint = "Non-text chat-completions response"
            if reasoning:
                hint = "Reasoning-only chat-completions response"
            raise LLMError(
                f"{hint} from {self.base_url}{last_detail}. "
                "The model may have spent the token budget on reasoning; "
                "increase max_tokens or choose a non-reasoning model."
            )

        raise LLMError(
            f"Non-text chat-completions response from {self.base_url}{last_detail}. "
            "The model may have spent the token budget on reasoning; "
            "increase max_tokens or choose a non-reasoning model."
        )

    def _payload(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float | None,
        max_tokens: int,
        disable_reasoning: bool,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2 if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        if disable_reasoning:
            # Free routing may otherwise pick a reasoning model that spends the
            # whole token budget thinking and returns no visible text. Models
            # that require reasoning reject this; the caller retries without it.
            payload["reasoning"] = {"enabled": False}
        return payload

    def _post(self, payload: dict, headers: dict[str, str]) -> dict:
        url = f"{self.base_url}/chat/completions"
        try:
            with HttpClient(
                timeout=self.timeout,
                retries=0,
                user_agent="jobscraper/0.1",
                transport=self.transport,
            ) as client:
                return client.post_json(url, payload, headers=headers)
        except Exception as exc:  # noqa: BLE001 - wrap transport/HTTP errors
            raise LLMError(f"OpenAI-compatible request failed: {exc}") from exc


def normalize_openai_base_url(value: str) -> str:
    """Accept a base URL or a full chat/responses endpoint.

    OpenRouter documents its base as ``https://openrouter.ai/api/v1`` but users
    often paste ``.../responses``. Strip known endpoint suffixes so the client
    always appends ``/chat/completions`` exactly once.
    """
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_BASE_URL
    lowered = cleaned.casefold()
    for suffix in ("/chat/completions", "/completions", "/responses"):
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].rstrip("/")
            break
    return cleaned or DEFAULT_BASE_URL


def _retry_token_budget(current: int) -> int:
    return min(max(current * 2, 512), _MAX_RETRY_TOKENS)


def _is_reasoning_mandatory_error(exc: Exception) -> bool:
    message = str(exc).casefold()
    return "reasoning" in message and (
        "mandatory" in message or "cannot be disabled" in message or "cannot disable" in message
    )

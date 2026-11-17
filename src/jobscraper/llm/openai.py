"""OpenAI-compatible chat-completions provider."""

from __future__ import annotations

import httpx

from ..utils.errors import LLMError
from ..utils.http import HttpClient


class OpenAICompatibleProvider:
    """Works with OpenAI, LM Studio, vLLM, and other compatible servers."""

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") or "https://api.openai.com/v1"
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
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2 if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            with HttpClient(
                timeout=self.timeout,
                retries=0,
                user_agent="jobscraper/0.1",
                transport=self.transport,
            ) as client:
                data = client.post_json(url, payload, headers=headers)
        except Exception as exc:  # noqa: BLE001 - wrap transport/HTTP errors
            raise LLMError(f"OpenAI-compatible request failed: {exc}") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected chat-completions response from {self.base_url}") from exc
        if not isinstance(content, str):
            raise LLMError(f"Non-text chat-completions response from {self.base_url}")
        return content.strip()

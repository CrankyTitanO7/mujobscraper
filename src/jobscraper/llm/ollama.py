"""Ollama native chat provider."""

from __future__ import annotations

import httpx

from ..utils.errors import LLMError
from ..utils.http import HttpClient


class OllamaProvider:
    """Local Ollama server; no API key or model download is performed."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") or "http://localhost:11434"
        self.model = model
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
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0.2 if temperature is None else temperature,
                "num_predict": max_tokens,
            },
        }
        url = f"{self.base_url}/api/chat"
        try:
            with HttpClient(
                timeout=self.timeout,
                retries=0,
                user_agent="jobscraper/0.1",
                transport=self.transport,
            ) as client:
                data = client.post_json(url, payload)
        except Exception as exc:  # noqa: BLE001 - wrap transport/HTTP errors
            raise LLMError(f"Ollama request failed: {exc}") from exc
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Ollama response from {self.base_url}") from exc
        if not isinstance(content, str):
            raise LLMError(f"Non-text Ollama response from {self.base_url}")
        return content.strip()

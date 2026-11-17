"""LLM provider interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal chat-completion interface shared by all providers."""

    name: str

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Return the assistant's text response."""

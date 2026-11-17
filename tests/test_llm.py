"""LLM provider and prompt tests (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from jobscraper.config import Config
from jobscraper.llm.factory import build_provider, resolve_settings
from jobscraper.llm.ollama import OllamaProvider
from jobscraper.llm.openai import OpenAICompatibleProvider
from jobscraper.llm.prompts import (
    UNKNOWN_MARKER,
    build_answer_prompt,
    build_extraction_prompt,
    is_unknown,
    parse_json_array,
)
from jobscraper.utils.errors import LLMError, LLMUnavailableError


def test_openai_provider_request_and_response() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "  Hello there  "}}]})

    provider = OpenAICompatibleProvider(
        base_url="https://api.example.com/v1",
        model="test-model",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    answer = provider.complete("system", "prompt", temperature=0.1, max_tokens=42)
    assert answer == "Hello there"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["auth"] == "Bearer secret"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["temperature"] == 0.1
    assert captured["body"]["max_tokens"] == 42
    assert "reasoning" not in captured["body"]


def test_openrouter_provider_disables_reasoning() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/free",
        transport=httpx.MockTransport(handler),
    )
    assert provider.complete("system", "prompt") == "ok"
    assert captured["body"]["reasoning"] == {"enabled": False}


def test_openrouter_retries_without_reasoning_when_mandatory() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if "reasoning" in body:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Reasoning is mandatory for this endpoint and cannot be disabled."
                    }
                },
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/free",
        transport=httpx.MockTransport(handler),
    )
    assert provider.complete("system", "prompt", max_tokens=300) == "ok"
    assert len(bodies) == 2
    assert bodies[0]["reasoning"] == {"enabled": False}
    assert "reasoning" not in bodies[1]
    assert [body["max_tokens"] for body in bodies] == [300, 600]


def test_openai_provider_retries_when_reasoning_exhausts_budget() -> None:
    budgets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        budgets.append(body["max_tokens"])
        if len(budgets) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": None, "reasoning": "thinking..."},
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/free",
        transport=httpx.MockTransport(handler),
    )
    assert provider.complete("system", "prompt", max_tokens=300) == "ok"
    assert budgets == [300, 600]


def test_openai_provider_handles_bad_response() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://api.example.com/v1",
        model="test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": True})
        ),
    )
    with pytest.raises(LLMError, match="Unexpected"):
        provider.complete("system", "prompt")


def test_openai_provider_normalizes_endpoint_suffixes() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    bases = [
        "https://openrouter.ai/api/v1/responses",
        "https://openrouter.ai/api/v1/chat/completions",
        "https://openrouter.ai/api/v1/completions",
        "https://openrouter.ai/api/v1/",
    ]
    for base in bases:
        provider = OpenAICompatibleProvider(
            base_url=base,
            model="openrouter/free",
            transport=httpx.MockTransport(handler),
        )
        assert provider.complete("system", "prompt") == "ok"
    assert urls == ["https://openrouter.ai/api/v1/chat/completions"] * len(bases)


def test_openai_provider_reports_reasoning_only_response() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": None, "reasoning": "thinking..."},
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/free",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMError, match="reasoning"):
        provider.complete("system", "prompt", max_tokens=10)
    assert calls == 3


def test_ollama_provider_request() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "Local answer"}})

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        model="llama3.1",
        transport=httpx.MockTransport(handler),
    )
    assert provider.complete("system", "prompt", max_tokens=20) == "Local answer"
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["model"] == "llama3.1"
    assert captured["body"]["stream"] is False


def test_factory_auto_with_key(config: Config) -> None:
    settings = resolve_settings(
        config,
        {
            "JOBSCRAPER_LLM_API_KEY": "key",
            "JOBSCRAPER_LLM_MODEL": "gpt-test",
        },
    )
    assert settings.provider == "openai"
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.model == "gpt-test"


def test_factory_normalizes_openai_endpoint(config: Config) -> None:
    settings = resolve_settings(
        config,
        {
            "JOBSCRAPER_LLM_PROVIDER": "openai",
            "JOBSCRAPER_LLM_BASE_URL": "https://openrouter.ai/api/v1/responses",
            "JOBSCRAPER_LLM_MODEL": "openrouter/free",
            "JOBSCRAPER_LLM_API_KEY": "key",
        },
    )
    assert settings.provider == "openai"
    assert settings.base_url == "https://openrouter.ai/api/v1"


def test_factory_auto_official_without_key_is_unavailable(config: Config) -> None:
    settings = resolve_settings(
        config,
        {
            "JOBSCRAPER_LLM_BASE_URL": "https://api.openai.com/v1",
            "JOBSCRAPER_LLM_MODEL": "gpt-test",
        },
    )
    assert settings.provider == "none"


def test_factory_auto_ollama_host(config: Config) -> None:
    settings = resolve_settings(
        config,
        {"OLLAMA_HOST": "http://localhost:11434", "JOBSCRAPER_LLM_MODEL": "llama3.1"},
    )
    assert settings.provider == "ollama"
    assert settings.base_url == "http://localhost:11434"


def test_factory_none_raises(config: Config) -> None:
    with pytest.raises(LLMUnavailableError, match="No LLM provider"):
        build_provider(config, {"JOBSCRAPER_LLM_PROVIDER": "none"})


def test_factory_missing_model_raises(config: Config) -> None:
    with pytest.raises(LLMUnavailableError, match="model is not configured"):
        build_provider(
            config,
            {"JOBSCRAPER_LLM_PROVIDER": "openai", "JOBSCRAPER_LLM_API_KEY": "key"},
        )


def test_factory_local_openai_without_key(config: Config) -> None:
    provider = build_provider(
        config,
        {
            "JOBSCRAPER_LLM_PROVIDER": "openai",
            "JOBSCRAPER_LLM_BASE_URL": "http://localhost:8000/v1",
            "JOBSCRAPER_LLM_MODEL": "local",
        },
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        ),
    )
    assert provider.name == "openai"
    assert provider.complete("s", "p") == "ok"


def test_prompt_contains_profile_job_reference_and_boolean_rule() -> None:
    system, prompt = build_answer_prompt(
        profile={"name": "Ada", "email": "ada@example.com", "links": {}},
        job={"company": "Acme", "title": "ML Intern", "tags": ["python"]},
        question="Are you authorized?",
        kind="boolean",
        options=["Yes", "No"],
        reference_answer="true",
        resume="Resume text",
        max_resume_chars=100,
    )
    assert "Ada" in system or "Ada" in prompt
    assert "Acme" in prompt
    assert "`true` or `false`" in prompt
    assert "PREVIOUSLY APPROVED ANSWER" in prompt
    assert UNKNOWN_MARKER in prompt


def test_extraction_prompt_and_json_parsing() -> None:
    _, prompt = build_extraction_prompt(
        job={"company": "Acme", "title": "ML Intern"},
        fields=[{"field_ref": "why", "label": "Why?", "kind": "free_text", "options": []}],
    )
    assert "field_ref" in prompt
    parsed = parse_json_array('```json\n[{"field_ref": "why", "question": "Why?"}]\n```')
    assert parsed == [{"field_ref": "why", "question": "Why?"}]
    with pytest.raises(ValueError):
        parse_json_array("not json")
    assert is_unknown("I cannot answer [[UNKNOWN]]")

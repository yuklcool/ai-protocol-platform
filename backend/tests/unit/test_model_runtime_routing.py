"""Agent-level tests for dynamic model provider routing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from adk import agent


def _dynamic_entry(**overrides):
    data = {
        "api_name": "deepseek-chat",
        "tier": "smart",
        "supports_reasoning": False,
        "supports_responses_api": False,
        "location": None,
        "residency": "global",
        "fallbacks": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_resolve_model_passes_provider_specific_runtime_kwargs_to_litellm() -> None:
    entry = _dynamic_entry()
    with (
        patch("adk.agent.entry_for", return_value=entry),
        patch("adk.agent.provider_for", return_value="openai"),
        patch(
            "adk.agent.openai_runtime_kwargs",
            return_value={"api_base": "https://api.deepseek.com/v1", "api_key": "secret"},
        ) as runtime,
        patch("adk.agent.LiteLlm") as lite,
    ):
        agent.resolve_model("deepseek-v3")

    runtime.assert_called_once_with("deepseek-v3")
    lite.assert_called_once_with(
        model="openai/deepseek-chat",
        api_base="https://api.deepseek.com/v1",
        api_key="secret",
    )


def test_resolve_model_merges_reasoning_capabilities_with_provider_runtime() -> None:
    entry = _dynamic_entry(supports_reasoning=True, supports_responses_api=True)
    with (
        patch("adk.agent.entry_for", return_value=entry),
        patch("adk.agent.provider_for", return_value="openai"),
        patch(
            "adk.agent.openai_runtime_kwargs",
            return_value={"api_base": "http://vllm:8000/v1", "api_key": "secret"},
        ),
        patch("adk.agent.LiteLlm") as lite,
    ):
        agent.resolve_model("reasoner")

    lite.assert_called_once_with(
        model="openai/deepseek-chat",
        api_base="http://vllm:8000/v1",
        api_key="secret",
        reasoning_effort="high",
        reasoning={"summary": "auto"},
        allowed_openai_params=["reasoning"],
    )


def test_fallback_key_check_delegates_to_dynamic_provider_resolver() -> None:
    with patch("adk.agent.provider_key_missing", return_value="${DEEPSEEK_API_KEY}") as missing:
        result = agent._provider_key_missing("deepseek-v3")

    assert result == "${DEEPSEEK_API_KEY}"
    missing.assert_called_once_with("deepseek-v3")

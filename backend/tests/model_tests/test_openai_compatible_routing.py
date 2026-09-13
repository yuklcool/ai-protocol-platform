"""Provider-driven OpenAI-compatible routing regression tests."""

import pytest

import adk.agent as agent
from config.models import ModelEntry


def _entry(**overrides):
    data = dict(
        id="deepseek-v3",
        api_name="deepseek-chat",
        provider="openai",
        tier="default",
        residency="global",
        context_window=128_000,
        max_output_tokens=8_192,
        description="test compatible model",
        supports_tools=True,
        supports_reasoning=False,
        supports_responses_api=False,
    )
    data.update(overrides)
    return ModelEntry(**data)


def _patch_registry(monkeypatch, entry):
    monkeypatch.setattr(agent, "entry_for", lambda _ref: entry)
    monkeypatch.setattr(agent, "api_name_for", lambda _ref: entry.api_name)
    monkeypatch.setattr(agent, "provider_for", lambda _ref: entry.provider)


def test_non_gpt_name_routes_by_provider(monkeypatch):
    entry = _entry()
    _patch_registry(monkeypatch, entry)
    seen = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(agent, "LiteLlm", FakeLiteLlm)
    monkeypatch.setenv("OPENAI_API_BASE", "http://model-gateway:8000/v1")
    agent.resolve_model("deepseek-v3")

    assert seen["model"] == "openai/deepseek-chat"
    assert seen["api_base"] == "http://model-gateway:8000/v1"
    assert "reasoning_effort" not in seen


def test_reasoning_capabilities_control_responses_bridge(monkeypatch):
    entry = _entry(
        id="reasoner",
        api_name="custom-reasoner",
        supports_reasoning=True,
        supports_responses_api=True,
        tier="smart",
    )
    _patch_registry(monkeypatch, entry)
    seen = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(agent, "LiteLlm", FakeLiteLlm)
    agent.resolve_model("reasoner")

    assert seen["model"] == "openai/custom-reasoner"
    assert seen["reasoning_effort"] == "high"
    assert seen["reasoning"] == {"summary": "auto"}
    assert seen["allowed_openai_params"] == ["reasoning"]


def test_reasoning_without_responses_stays_on_chat_compatible_path(monkeypatch):
    entry = _entry(
        id="chat-reasoner",
        api_name="chat-reasoner",
        supports_reasoning=True,
        supports_responses_api=False,
    )
    _patch_registry(monkeypatch, entry)
    seen = {}

    class FakeLiteLlm:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(agent, "LiteLlm", FakeLiteLlm)
    agent.resolve_model("chat-reasoner")

    assert seen["reasoning_effort"] == "medium"
    assert "reasoning" not in seen
    assert "allowed_openai_params" not in seen


def test_unregistered_nonstandard_name_fails_with_registry_hint(monkeypatch):
    monkeypatch.setattr(agent, "entry_for", lambda _ref: None)
    monkeypatch.setattr(agent, "api_name_for", lambda ref: ref)
    monkeypatch.setattr(agent, "provider_for", lambda _ref: None)
    with pytest.raises(ValueError, match="Register non-standard model names"):
        agent.resolve_model("deepseek-chat")

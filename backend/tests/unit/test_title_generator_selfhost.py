from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from db.title_generator import generate_title_fast


def _event(author, text):
    return SimpleNamespace(author=author, content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))


def test_selfhost_title_uses_user_text_without_constructing_cloud_client(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.delenv("CHAT_TITLE_MODEL", raising=False)
    with patch("google.genai.Client", side_effect=AssertionError("Unconfigured provider")) as client:
        assert generate_title_fast([_event("user", "Review the current protocol operation status")]) == (
            "Review the current protocol operation status"
        )
        client.assert_not_called()


def test_selfhost_title_does_not_copy_assistant_only_content(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.delenv("CHAT_TITLE_MODEL", raising=False)
    with patch("google.genai.Client", side_effect=AssertionError("Unconfigured provider")):
        assert generate_title_fast([_event("root_agent", "No user turn yet")]) is None


def test_title_registry_failure_is_optional(monkeypatch):
    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.setenv("CHAT_TITLE_MODEL", "explicit-gemini-title")
    with patch("config.models.api_name_for", side_effect=ValueError("Invalid model")):
        assert generate_title_fast([_event("user", "Review protocol status")]) is None


@pytest.mark.parametrize("vertex, expected_kwargs", [("false", {}), ("true", {"location": "global"})])
def test_explicit_title_model_respects_transport_and_closes_client(monkeypatch, vertex, expected_kwargs):
    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.setenv("CHAT_TITLE_MODEL", "explicit-gemini-title")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", vertex)
    client = MagicMock()
    client.models.generate_content.return_value.text = "Protocol operation status"
    with (
        patch("config.models.api_name_for", return_value="gemini-title"),
        patch("config.models.entry_for", return_value=SimpleNamespace(location="global", residency="global")),
        patch("config.thinking.thinking_config_for", return_value=None),
        patch("google.genai.Client", return_value=client) as constructor,
    ):
        assert generate_title_fast([_event("user", "Review protocol status")]) == "Protocol operation status"
        constructor.assert_called_once_with(**expected_kwargs)
        client.close.assert_called_once()

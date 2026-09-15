"""Hermetic tests for dynamic model-provider registry helpers."""

from __future__ import annotations

import pytest

from config import model_provider_registry as registry


def test_database_registry_defaults_on_for_self_host(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_REGISTRY_BACKEND", raising=False)
    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    assert registry.database_registry_enabled() is True


def test_explicit_yaml_backend_disables_database_overlay(monkeypatch) -> None:
    monkeypatch.setenv("SELF_HOSTED_MODE", "1")
    monkeypatch.setenv("MODEL_REGISTRY_BACKEND", "yaml")
    assert registry.database_registry_enabled() is False


def test_secret_reference_resolves_environment(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER_TEST_KEY", "TEST_SECRET_VALUE")
    assert registry.resolve_api_key_ref("${MODEL_PROVIDER_TEST_KEY}") == "TEST_SECRET_VALUE"


def test_plaintext_secret_reference_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="plaintext API keys"):
        registry.resolve_api_key_ref("PLAINTEXT_KEY")


def test_missing_secret_reference_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_PROVIDER_KEY", raising=False)
    with pytest.raises(RuntimeError, match="unset or empty"):
        registry.resolve_api_key_ref("${MISSING_PROVIDER_KEY}")

"""Unit tests for canonical tenant model policy semantics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config.tenant_models import (
    TenantModelAccessError,
    TenantModelPolicy,
    assert_model_allowed,
    load_tenant_model_policy,
    validate_tenant_model_policy,
)


def test_missing_allowlist_is_backward_compatible_unrestricted() -> None:
    policy = TenantModelPolicy.model_validate({})
    assert policy.restricted is False
    assert policy.allows("any-model") is True


def test_explicit_empty_allowlist_is_deny_all() -> None:
    policy = TenantModelPolicy(allowedModels=[])
    assert policy.restricted is True
    assert policy.allows("gpt-5") is False
    with pytest.raises(TenantModelAccessError):
        assert_model_allowed("gpt-5", tenant_id="tenant-a", policy=policy)


def test_policy_normalizes_duplicates_and_blank_values() -> None:
    policy = TenantModelPolicy(
        allowedModels=["model-a", " model-a ", "", "model-b"],
        defaultModel=" model-b ",
    )
    assert policy.allowed_models == ["model-a", "model-b"]
    assert policy.default_model == "model-b"


def test_validation_rejects_unknown_and_default_outside_whitelist() -> None:
    policy = TenantModelPolicy(
        allowedModels=["model-a", "missing"],
        defaultModel="model-b",
    )
    errors = validate_tenant_model_policy(policy, ["model-a", "model-b"])
    assert any("missing" in message for message in errors)
    assert any("defaultModel" in message for message in errors)


def test_disabled_tenant_is_runtime_deny_all() -> None:
    tenant = SimpleNamespace(disabled=True, model_policy={})
    with patch("config.tenant_models.get_tenant", return_value=tenant):
        policy = load_tenant_model_policy("tenant-disabled")
    assert policy.allowed_models == []


def test_first_class_policy_is_loaded_without_dropping_extension_fields() -> None:
    tenant = SimpleNamespace(
        disabled=False,
        model_policy={
            "allowedModels": ["model-a"],
            "defaultModel": "model-a",
            "allowedProviders": ["openai-compatible"],
        },
    )
    with patch("config.tenant_models.get_tenant", return_value=tenant):
        policy = load_tenant_model_policy("tenant-a")
    dumped = policy.model_dump(by_alias=True, exclude_none=True)
    assert dumped["allowedModels"] == ["model-a"]
    assert dumped["defaultModel"] == "model-a"
    assert dumped["allowedProviders"] == ["openai-compatible"]

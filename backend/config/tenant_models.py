"""Tenant-scoped model access policy over the effective model registry.

The durable source is ``tenants/{tenant_id}.modelPolicy``. A missing
``allowedModels`` key means unrestricted access for backward compatibility;
an explicitly empty list means the tenant may not use any model. Model ids in
this policy are always effective-registry ids, never provider API names.

Runtime callers recover the trusted tenant id from ``tenant_context``. This
keeps model authorization server-authoritative and prevents request payloads or
frontend state from selecting another tenant's policy.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.tenants import get_tenant


class TenantModelAccessError(ValueError):
    """Raised when a resolved model is outside the active tenant policy."""


class TenantModelPolicy(BaseModel):
    """Canonical tenant model policy while preserving future/legacy extensions."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    allowed_models: list[str] | None = Field(default=None, alias="allowedModels")
    default_model: str | None = Field(default=None, alias="defaultModel")

    @field_validator("allowed_models")
    @classmethod
    def _normalize_allowed_models(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        result: list[str] = []
        seen: set[str] = set()
        for raw in value:
            model_id = str(raw or "").strip()
            if not model_id or model_id in seen:
                continue
            result.append(model_id)
            seen.add(model_id)
        return result

    @field_validator("default_model")
    @classmethod
    def _normalize_default_model(cls, value: str | None) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None

    @property
    def restricted(self) -> bool:
        """Whether an explicit allow-list is active."""
        return self.allowed_models is not None

    def allows(self, model_id: str) -> bool:
        if self.allowed_models is None:
            return True
        return model_id in set(self.allowed_models)


def _trusted_current_tenant_id() -> str:
    # Lazy import is deliberate: runtime model metadata is imported during
    # backend startup, while tenant_context currently carries provider-specific
    # auth typing. Self-host startup must not eagerly pull a cloud auth path just
    # because model policy support is installed.
    from observability.tenant_context import get_current_tenant_id

    return get_current_tenant_id()


def tenant_id_for_user(user: object | None) -> str:
    if user is None:
        return ""
    tenant_id = str(getattr(user, "tenant_id", "") or "").strip()
    if tenant_id:
        return tenant_id
    # Domain is a migration-only fallback already used by the trusted auth
    # tenant context. New identities should always carry tenant_id.
    return str(getattr(user, "domain", "") or "").strip()


def load_tenant_model_policy(tenant_id: str | None = None) -> TenantModelPolicy:
    """Load policy for an explicit or trusted task-local tenant id.

    No tenant context and unknown legacy tenants remain unrestricted to preserve
    existing non-tenant metadata/admin call sites. A disabled first-class
    tenant is treated as an explicit deny-all policy as an additional runtime
    safety boundary.
    """

    stable_id = (tenant_id if tenant_id is not None else _trusted_current_tenant_id()).strip()
    if not stable_id:
        return TenantModelPolicy()
    tenant = get_tenant(stable_id)
    if tenant is None:
        return TenantModelPolicy()
    if tenant.disabled:
        return TenantModelPolicy(allowedModels=[])
    return TenantModelPolicy.model_validate(tenant.model_policy or {})


def validate_tenant_model_policy(
    policy: TenantModelPolicy,
    available_model_ids: Iterable[str],
) -> list[str]:
    """Return human-readable validation errors against the effective registry."""

    available = {str(value) for value in available_model_ids}
    errors: list[str] = []
    if policy.allowed_models is not None:
        unknown = sorted(set(policy.allowed_models) - available)
        if unknown:
            errors.append(f"Unknown or disabled allowed model id(s): {', '.join(unknown)}")
    if policy.default_model:
        if policy.default_model not in available:
            errors.append(f"Unknown or disabled default model id: {policy.default_model}")
        if policy.allowed_models is not None and policy.default_model not in set(policy.allowed_models):
            errors.append("defaultModel must also be present in allowedModels when a whitelist is configured")
    return errors


def assert_model_allowed(
    model_id: str,
    *,
    tenant_id: str | None = None,
    policy: TenantModelPolicy | None = None,
) -> None:
    active = policy or load_tenant_model_policy(tenant_id)
    if active.allows(model_id):
        return
    stable_id = tenant_id if tenant_id is not None else _trusted_current_tenant_id()
    raise TenantModelAccessError(
        f"Model {model_id!r} is not allowed for tenant {stable_id or '(unknown)'!r}"
    )


def filter_allowed_model_ids(
    model_ids: Iterable[str],
    *,
    tenant_id: str | None = None,
    policy: TenantModelPolicy | None = None,
) -> list[str]:
    active = policy or load_tenant_model_policy(tenant_id)
    return [model_id for model_id in model_ids if active.allows(model_id)]


__all__ = [
    "TenantModelAccessError",
    "TenantModelPolicy",
    "assert_model_allowed",
    "filter_allowed_model_ids",
    "load_tenant_model_policy",
    "tenant_id_for_user",
    "validate_tenant_model_policy",
]

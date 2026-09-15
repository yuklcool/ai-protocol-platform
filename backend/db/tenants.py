"""First-class tenant directory with legacy domain-model compatibility.

Phase 3 moves tenant identity away from ``clients/{email-domain}`` toward a
stable tenant primary key.  The durable model is split into:

* ``tenants/{tenant_id}`` — tenant configuration and policy.
* ``tenant_domains/{domain}`` — optional identity-domain -> tenant mapping.

The directory is backend-neutral because it depends only on the Repository
contract.  Reads retain a compatibility bridge for historical
``clients/{domain}`` records, so deployments can migrate one tenant at a time
without changing all callers in one release.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from db.persistence import get_repository
from db.repository import Repository

TENANT_COLLECTION = "tenants"
DOMAIN_MAPPING_COLLECTION = "tenant_domains"
LEGACY_CLIENT_COLLECTION = "clients"


def normalize_tenant_id(value: str) -> str:
    """Normalize a stable tenant key without imposing email-domain semantics."""
    return (value or "").strip()


def normalize_domain(value: str) -> str:
    return (value or "").strip().casefold().rstrip(".")


class TenantConfig(BaseModel):
    """Provider-neutral tenant configuration.

    ``domains`` is only an identity mapping aid.  It is not the tenant primary
    key and may be empty for OIDC/JWT tenants that identify themselves through
    a trusted tenant claim.
    """

    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    display_name: str = Field(default="", alias="displayName")
    domains: list[str] = Field(default_factory=list)
    enabled_skills: list[str] | None = Field(default=None, alias="enabledSkills")
    default_skill: str | None = Field(default=None, alias="defaultSkill")
    derived_group_tags: list[str] | None = Field(default=None, alias="derivedGroupTags")
    model_policy: dict[str, Any] = Field(default_factory=dict, alias="modelPolicy")
    storage_namespace: str = Field(default="", alias="storageNamespace")
    documents_bucket: str | None = Field(default=None, alias="documentsBucket")
    quota: dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False

    def normalized(self) -> "TenantConfig":
        tenant_id = normalize_tenant_id(self.tenant_id)
        if not tenant_id:
            raise ValueError("tenant_id must be non-empty")
        domains = sorted({d for d in (normalize_domain(v) for v in self.domains) if d})
        namespace = self.storage_namespace.strip() or tenant_id
        return self.model_copy(
            update={
                "tenant_id": tenant_id,
                "domains": domains,
                "storage_namespace": namespace,
            }
        )


class TenantDirectory:
    """Repository-backed tenant registry and domain mapping.

    The class takes an explicit Repository to keep migration tools and tests
    deterministic.  Runtime helpers below use the configured persistence
    repository.
    """

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def get(self, tenant_id: str) -> TenantConfig | None:
        key = normalize_tenant_id(tenant_id)
        if not key:
            return None
        data = self._repository.get_document(TENANT_COLLECTION, key)
        if data is not None:
            return TenantConfig.model_validate({**data, "tenantId": key}).normalized()

        # Legacy bridge: historically tenant config lived in clients/{domain}.
        # Treat that domain as the temporary stable id until migrated.
        legacy = self._repository.get_document(LEGACY_CLIENT_COLLECTION, key)
        if legacy is None:
            return None
        return self._legacy_config(key, legacy)

    def tenant_id_for_domain(self, domain: str) -> str | None:
        normalized = normalize_domain(domain)
        if not normalized:
            return None
        mapping = self._repository.get_document(DOMAIN_MAPPING_COLLECTION, normalized)
        if mapping is not None:
            tenant_id = normalize_tenant_id(str(mapping.get("tenantId") or ""))
            return tenant_id or None

        # Legacy compatibility: a clients/{domain} record implies a tenant whose
        # temporary id is that domain.  Unknown domains remain unmapped rather
        # than being invented automatically.
        if self._repository.get_document(LEGACY_CLIENT_COLLECTION, normalized) is not None:
            return normalized
        return None

    def get_by_domain(self, domain: str) -> TenantConfig | None:
        tenant_id = self.tenant_id_for_domain(domain)
        return self.get(tenant_id) if tenant_id else None

    def put(self, config: TenantConfig) -> TenantConfig:
        normalized = config.normalized()
        tenant_id = normalized.tenant_id
        previous = self._repository.get_document(TENANT_COLLECTION, tenant_id)
        previous_domains = {
            normalize_domain(v)
            for v in ((previous or {}).get("domains") or [])
            if normalize_domain(v)
        }
        current_domains = set(normalized.domains)

        self._repository.set_document(
            TENANT_COLLECTION,
            tenant_id,
            normalized.model_dump(by_alias=True, exclude_none=True),
        )

        for domain in current_domains:
            existing = self._repository.get_document(DOMAIN_MAPPING_COLLECTION, domain)
            if existing is not None:
                owner = normalize_tenant_id(str(existing.get("tenantId") or ""))
                if owner and owner != tenant_id:
                    raise ValueError(f"domain {domain!r} is already mapped to tenant {owner!r}")
            self._repository.set_document(
                DOMAIN_MAPPING_COLLECTION,
                domain,
                {"domain": domain, "tenantId": tenant_id},
            )

        for domain in previous_domains - current_domains:
            existing = self._repository.get_document(DOMAIN_MAPPING_COLLECTION, domain)
            if existing is not None and existing.get("tenantId") == tenant_id:
                self._repository.delete_document(DOMAIN_MAPPING_COLLECTION, domain)

        return normalized

    def set_disabled(self, tenant_id: str, disabled: bool) -> TenantConfig | None:
        current = self.get(tenant_id)
        if current is None:
            return None
        updated = current.model_copy(update={"disabled": bool(disabled)})
        return self.put(updated)

    @staticmethod
    def _legacy_config(domain: str, legacy: dict[str, Any]) -> TenantConfig:
        return TenantConfig(
            tenantId=domain,
            displayName=str(legacy.get("display_name") or legacy.get("displayName") or ""),
            domains=[domain],
            enabledSkills=legacy.get("enabled_skills") or legacy.get("enabledSkills"),
            defaultSkill=legacy.get("default_skill") or legacy.get("defaultSkill"),
            derivedGroupTags=legacy.get("derived_group_tags") or legacy.get("derivedGroupTags"),
            documentsBucket=legacy.get("documents_bucket") or legacy.get("documentsBucket"),
            storageNamespace=domain,
        ).normalized()


def get_tenant(tenant_id: str) -> TenantConfig | None:
    return TenantDirectory(get_repository()).get(tenant_id)


def tenant_id_for_domain(domain: str) -> str | None:
    return TenantDirectory(get_repository()).tenant_id_for_domain(domain)


def get_tenant_by_domain(domain: str) -> TenantConfig | None:
    return TenantDirectory(get_repository()).get_by_domain(domain)


def put_tenant(config: TenantConfig) -> TenantConfig:
    return TenantDirectory(get_repository()).put(config)


__all__ = [
    "DOMAIN_MAPPING_COLLECTION",
    "LEGACY_CLIENT_COLLECTION",
    "TENANT_COLLECTION",
    "TenantConfig",
    "TenantDirectory",
    "get_tenant",
    "get_tenant_by_domain",
    "normalize_domain",
    "normalize_tenant_id",
    "put_tenant",
    "tenant_id_for_domain",
]
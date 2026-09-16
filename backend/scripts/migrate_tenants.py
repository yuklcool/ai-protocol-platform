#!/usr/bin/env python3
"""Migrate legacy domain ownership into first-class stable tenants.

The migration is deliberately conservative and reversible:

* dry-run is the default; writes require ``--apply``;
* ``--map domain=tenant_id`` is the authoritative legacy-domain mapping;
* existing explicit local-user ``tenantId`` values are never overwritten from
  email/domain inference;
* domain tool rules become first-class ``tenant:<tenant_id>`` rules only when
  all merged legacy domains agree on the effective permission set;
* user tool-rule ownership is backfilled only when an exact local ``auth_users``
  record provides (or is safely assigned) the tenant;
* audit rows are backfilled only from explicit target ownership, trusted local
  user assignments, or this migration's explicit client-domain mapping;
* every apply run writes a field-level migration journal. ``--rollback RUN_ID``
  restores it only if the migrated data has not drifted since the run.

No ownership is inferred from ``actorEmail`` or an arbitrary historical email
address. Ambiguous legacy rows remain platform-only.

Examples:

  # Preview a zero-behavior-change migration.
  uv run python scripts/migrate_tenants.py

  # Merge two historical domains under one stable tenant id.
  uv run python scripts/migrate_tenants.py \
      --map acme.com=tenant-acme \
      --map acme-energy.example=tenant-acme \
      --require-explicit \
      --apply

  # Revert an applied run after reviewing drift checks.
  uv run python scripts/migrate_tenants.py --rollback <run-id>
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Iterator

from auth.admin_roles import TENANT_ADMIN_PREFIX
from auth.permissions import TENANT_PREFIX, tenant_permission_key
from db.persistence import get_repository
from db.repository import Repository
from db.tenants import TenantConfig, normalize_domain, normalize_tenant_id
from scripts.tenant_migration_journal import MigrationJournal, rollback_migration

CLIENT_COLLECTION = "clients"
TENANT_COLLECTION = "tenants"
DOMAIN_COLLECTION = "tenant_domains"
AUTH_USER_COLLECTION = "auth_users"
TOOL_PERMISSION_COLLECTION = "tool_permissions"
AUDIT_COLLECTION = "admin_audit"


@dataclass
class PlannedTenant:
    tenant_id: str
    domains: set[str] = field(default_factory=set)
    display_name: str = ""
    enabled_skills: list[str] | None = None
    default_skill: str | None = None
    derived_group_tags: list[str] | None = None
    documents_bucket: str | None = None

    def merge_legacy(self, domain: str, row: dict[str, Any]) -> None:
        self.domains.add(domain)
        self.display_name = _merge_scalar(
            "display_name",
            self.display_name,
            str(row.get("display_name") or row.get("displayName") or ""),
            self.tenant_id,
        )
        self.default_skill = _merge_scalar(
            "default_skill",
            self.default_skill,
            row.get("default_skill") or row.get("defaultSkill"),
            self.tenant_id,
        )
        self.documents_bucket = _merge_scalar(
            "documents_bucket",
            self.documents_bucket,
            row.get("documents_bucket") or row.get("documentsBucket"),
            self.tenant_id,
        )
        self.enabled_skills = _merge_list(
            "enabled_skills",
            self.enabled_skills,
            row.get("enabled_skills") or row.get("enabledSkills"),
            self.tenant_id,
        )
        self.derived_group_tags = _merge_list(
            "derived_group_tags",
            self.derived_group_tags,
            row.get("derived_group_tags") or row.get("derivedGroupTags"),
            self.tenant_id,
        )

    def config(self) -> TenantConfig:
        return TenantConfig(
            tenantId=self.tenant_id,
            displayName=self.display_name,
            domains=sorted(self.domains),
            enabledSkills=self.enabled_skills,
            defaultSkill=self.default_skill,
            derivedGroupTags=self.derived_group_tags,
            documentsBucket=self.documents_bucket,
            storageNamespace=self.tenant_id,
        ).normalized()


@dataclass
class PlannedUserUpdate:
    doc_id: str
    email: str
    tenant_id: str
    updates: dict[str, Any]
    permission_updates: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedPermission:
    tenant_id: str
    payload: dict[str, Any]
    existing_updates: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedAuditUpdate:
    doc_id: str
    tenant_id: str


@dataclass
class MigrationResult:
    configs: list[TenantConfig]
    users_updated: int = 0
    tenant_permissions_created: int = 0
    tenant_permissions_updated: int = 0
    user_permissions_updated: int = 0
    audits_updated: int = 0
    run_id: str | None = None

    # Preserve the historical ``configs, users_updated = migrate(...)`` API for
    # existing callers/tests while exposing richer production migration data.
    def __iter__(self) -> Iterator[Any]:
        yield self.configs
        yield self.users_updated

    def summary(self) -> dict[str, int]:
        return {
            "tenants": len(self.configs),
            "usersUpdated": self.users_updated,
            "tenantPermissionsCreated": self.tenant_permissions_created,
            "tenantPermissionsUpdated": self.tenant_permissions_updated,
            "userPermissionsUpdated": self.user_permissions_updated,
            "auditsUpdated": self.audits_updated,
        }


def _merge_scalar(field_name: str, current: Any, incoming: Any, tenant_id: str):
    if incoming in (None, ""):
        return current
    if current in (None, ""):
        return incoming
    if current != incoming:
        raise ValueError(
            f"tenant {tenant_id!r}: legacy domains disagree on {field_name}: "
            f"{current!r} != {incoming!r}"
        )
    return current


def _merge_list(field_name: str, current: list[str] | None, incoming: Any, tenant_id: str) -> list[str] | None:
    if incoming in (None, []):
        return current
    cleaned = [str(item) for item in incoming]
    if current is None:
        return cleaned
    if current != cleaned:
        raise ValueError(
            f"tenant {tenant_id!r}: legacy domains disagree on {field_name}: "
            f"{current!r} != {cleaned!r}"
        )
    return current


def parse_mapping(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --map {value!r}; expected domain=tenant_id")
        raw_domain, raw_tenant = value.split("=", 1)
        domain = normalize_domain(raw_domain)
        tenant_id = normalize_tenant_id(raw_tenant)
        if not domain or not tenant_id:
            raise ValueError(f"invalid --map {value!r}; both sides must be non-empty")
        previous = mapping.get(domain)
        if previous is not None and previous != tenant_id:
            raise ValueError(f"domain {domain!r} mapped to both {previous!r} and {tenant_id!r}")
        mapping[domain] = tenant_id
    return mapping


def build_migration_plan(
    rows: list[dict[str, Any]],
    mapping: dict[str, str] | None = None,
    *,
    require_explicit: bool = False,
) -> dict[str, PlannedTenant]:
    mapping = mapping or {}
    plan: dict[str, PlannedTenant] = {}
    for row in rows:
        domain = normalize_domain(str(row.get("__id") or row.get("domain") or ""))
        if not domain:
            raise ValueError(f"legacy clients row has no domain/document id: {row!r}")
        tenant_id = mapping.get(domain)
        if tenant_id is None:
            if require_explicit:
                raise ValueError(f"legacy domain {domain!r} has no explicit tenant mapping")
            tenant_id = domain
        tenant_id = normalize_tenant_id(tenant_id)
        planned = plan.setdefault(tenant_id, PlannedTenant(tenant_id=tenant_id))
        planned.merge_legacy(domain, row)
    return plan


def _domain_to_tenant(configs: list[TenantConfig]) -> dict[str, str]:
    result: dict[str, str] = {}
    for config in configs:
        for domain in config.domains:
            result[normalize_domain(domain)] = config.tenant_id
    return result


def _rewrite_tenant_admin_tags(
    tags: object,
    domain_mapping: dict[str, str],
) -> tuple[list[str], bool]:
    """Rewrite exact legacy tenant-admin domain grants to stable tenant ids."""
    raw = [str(tag) for tag in (tags or [])]
    rewritten: list[str] = []
    changed = False
    for tag in raw:
        if not tag.startswith(TENANT_ADMIN_PREFIX):
            rewritten.append(tag)
            continue
        suffix = tag[len(TENANT_ADMIN_PREFIX) :].strip()
        legacy_domain = normalize_domain(suffix)
        tenant_id = domain_mapping.get(legacy_domain)
        if not tenant_id:
            rewritten.append(tag)
            continue
        replacement = f"{TENANT_ADMIN_PREFIX}{tenant_id}"
        rewritten.append(replacement)
        changed = changed or replacement != tag

    deduped = sorted(set(rewritten))
    changed = changed or deduped != sorted(set(raw))
    return deduped, changed


def _tenant_document(config: TenantConfig) -> dict[str, Any]:
    return config.model_dump(by_alias=True, exclude_none=True)


def _preflight_directory(repository: Repository, configs: list[TenantConfig]) -> None:
    """Refuse to overwrite a first-class tenant or conflicting domain mapping."""
    for config in configs:
        expected = _tenant_document(config)
        existing_tenant = repository.get_document(TENANT_COLLECTION, config.tenant_id)
        if existing_tenant is not None and existing_tenant != expected:
            raise ValueError(
                f"tenant {config.tenant_id!r} already exists with different first-class configuration; "
                "migration will not overwrite it"
            )
        for domain in config.domains:
            existing_mapping = repository.get_document(DOMAIN_COLLECTION, domain)
            if existing_mapping is None:
                continue
            owner = normalize_tenant_id(str(existing_mapping.get("tenantId") or ""))
            if owner != config.tenant_id:
                raise ValueError(
                    f"domain {domain!r} is already mapped to tenant {owner!r}, not {config.tenant_id!r}"
                )


def _canonical_permission(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    tools = sorted({str(value) for value in (row.get("tools") or []) if str(value)})
    denied = sorted({str(value) for value in (row.get("denied") or []) if str(value)})
    return tools, denied


def _plan_tenant_permissions(
    repository: Repository,
    configs: list[TenantConfig],
) -> list[PlannedPermission]:
    planned: list[PlannedPermission] = []
    for config in configs:
        source: tuple[list[str], list[str]] | None = None
        source_domain = ""
        for domain in config.domains:
            legacy = repository.get_document(TOOL_PERMISSION_COLLECTION, domain)
            if legacy is None:
                continue
            current = _canonical_permission(legacy)
            if source is None:
                source = current
                source_domain = domain
            elif source != current:
                raise ValueError(
                    f"tenant {config.tenant_id!r}: legacy domain tool permissions disagree: "
                    f"{source_domain!r} != {domain!r}"
                )
        if source is None:
            continue

        tools, denied = source
        target_key = tenant_permission_key(config.tenant_id)
        payload = {
            "type": "tenant",
            "tools": tools,
            "denied": denied,
            "tenantId": config.tenant_id,
        }
        existing = repository.get_document(TOOL_PERMISSION_COLLECTION, target_key)
        updates: dict[str, Any] = {}
        if existing is not None:
            if str(existing.get("type") or "") != "tenant" or _canonical_permission(existing) != source:
                raise ValueError(
                    f"tenant permission {target_key!r} already exists with different rules"
                )
            explicit_owner = str(existing.get("tenantId") or "").strip()
            if explicit_owner and explicit_owner != config.tenant_id:
                raise ValueError(
                    f"tenant permission {target_key!r} claims conflicting tenantId {explicit_owner!r}"
                )
            if not explicit_owner:
                updates["tenantId"] = config.tenant_id
        planned.append(
            PlannedPermission(
                tenant_id=config.tenant_id,
                payload=payload,
                existing_updates=updates,
            )
        )
    return planned


def _plan_user_updates(
    repository: Repository,
    domain_mapping: dict[str, str],
) -> tuple[list[PlannedUserUpdate], dict[str, str]]:
    planned: list[PlannedUserUpdate] = []
    user_tenants: dict[str, str] = {}
    for row in repository.query_documents(AUTH_USER_COLLECTION, limit=None):
        doc_id = str(row.get("__id") or "").strip()
        if not doc_id:
            continue
        email = str(row.get("email") or "").strip().casefold()
        domain = normalize_domain(str(row.get("domain") or ""))
        explicit_tenant = normalize_tenant_id(str(row.get("tenantId") or ""))
        mapped_tenant = domain_mapping.get(domain, "") if domain else ""

        # Existing explicit identity ownership is authoritative. Never rewrite
        # it just because the account email happens to belong to a mapped domain.
        tenant_id = explicit_tenant or mapped_tenant
        updates: dict[str, Any] = {}
        if not explicit_tenant and mapped_tenant:
            updates["tenantId"] = mapped_tenant

        group_tags, tags_changed = _rewrite_tenant_admin_tags(row.get("groupTags") or [], domain_mapping)
        if tags_changed:
            updates["groupTags"] = group_tags

        permission_updates: dict[str, Any] = {}
        if email and tenant_id:
            user_tenants[email] = tenant_id
            permission = repository.get_document(TOOL_PERMISSION_COLLECTION, email)
            if permission is not None:
                permission_owner = normalize_tenant_id(str(permission.get("tenantId") or ""))
                if permission_owner and permission_owner != tenant_id:
                    raise ValueError(
                        f"user tool permission {email!r} belongs to {permission_owner!r}, "
                        f"but trusted auth user belongs to {tenant_id!r}"
                    )
                if not permission_owner:
                    permission_updates["tenantId"] = tenant_id

        if updates or permission_updates:
            planned.append(
                PlannedUserUpdate(
                    doc_id=doc_id,
                    email=email,
                    tenant_id=tenant_id,
                    updates=updates,
                    permission_updates=permission_updates,
                )
            )
    return planned, user_tenants


def _snapshot_tenant(snapshot: object, domain_mapping: dict[str, str]) -> str:
    if not isinstance(snapshot, dict):
        return ""
    raw = str(snapshot.get("tenantId") or snapshot.get("tenant_id") or "").strip()
    if not raw:
        return ""
    mapped = domain_mapping.get(normalize_domain(raw))
    return mapped or normalize_tenant_id(raw)


def _trusted_audit_tenant(
    row: dict[str, Any],
    *,
    domain_mapping: dict[str, str],
    user_tenants: dict[str, str],
    known_tenants: set[str],
) -> str:
    """Resolve target ownership only from explicit server-side evidence."""
    current = str(row.get("tenantId") or "").strip()
    if current:
        return domain_mapping.get(normalize_domain(current), normalize_tenant_id(current))

    for snapshot_name in ("after", "before"):
        owner = _snapshot_tenant(row.get(snapshot_name), domain_mapping)
        if owner:
            return owner

    action = str(row.get("action") or "")
    target = str(row.get("target") or "").strip()
    if not target:
        return ""

    # Legacy clients/{domain} administration is safely attributable because the
    # migration plan itself is the authoritative domain -> tenant mapping.
    if action in {"upsert_client", "delete_client"}:
        return domain_mapping.get(normalize_domain(target), "")

    if action in {
        "onboard_tenant",
        "edit_tenant",
        "disable_tenant",
        "enable_tenant",
        "update_tenant_model_policy",
    }:
        mapped = domain_mapping.get(normalize_domain(target), normalize_tenant_id(target))
        return mapped if mapped in known_tenants else ""

    if action in {"upsert_tool_permission", "delete_tool_permission"}:
        if target.startswith(TENANT_PREFIX):
            candidate = normalize_tenant_id(target[len(TENANT_PREFIX) :])
            return candidate if candidate in known_tenants else ""
        domain_owner = domain_mapping.get(normalize_domain(target))
        if domain_owner:
            return domain_owner
        return user_tenants.get(target.casefold(), "")

    # User admin audit can be attributed only when this exact email has a
    # trusted local auth record. Do not fall back to the email's domain.
    if action in {"grant_group_tag", "revoke_group_tag", "refresh_claims"}:
        return user_tenants.get(target.casefold(), "")

    return ""


def _plan_audit_updates(
    repository: Repository,
    *,
    domain_mapping: dict[str, str],
    user_tenants: dict[str, str],
    known_tenants: set[str],
) -> list[PlannedAuditUpdate]:
    planned: list[PlannedAuditUpdate] = []
    for row in repository.query_documents(AUDIT_COLLECTION, limit=None):
        doc_id = str(row.get("__id") or "").strip()
        if not doc_id:
            continue
        tenant_id = _trusted_audit_tenant(
            row,
            domain_mapping=domain_mapping,
            user_tenants=user_tenants,
            known_tenants=known_tenants,
        )
        if not tenant_id:
            continue
        if str(row.get("tenantId") or "").strip() == tenant_id:
            continue
        planned.append(PlannedAuditUpdate(doc_id=doc_id, tenant_id=tenant_id))
    return planned


def migrate(
    repository: Repository,
    mapping: dict[str, str],
    *,
    apply: bool,
    require_explicit: bool,
) -> MigrationResult:
    rows = repository.query_documents(CLIENT_COLLECTION, limit=None)
    plan = build_migration_plan(rows, mapping, require_explicit=require_explicit)
    configs = [plan[key].config() for key in sorted(plan)]
    domain_mapping = _domain_to_tenant(configs)

    # Complete conflict detection before the first write. The journal protects
    # interrupted runs; preflight keeps ordinary configuration mistakes from
    # producing a run that immediately needs rollback.
    _preflight_directory(repository, configs)
    tenant_permissions = _plan_tenant_permissions(repository, configs)
    user_updates, user_tenants = _plan_user_updates(repository, domain_mapping)
    known_tenants = {config.tenant_id for config in configs}
    known_tenants.update(
        normalize_tenant_id(str(row.get("__id") or ""))
        for row in repository.query_documents(TENANT_COLLECTION, limit=None)
        if str(row.get("__id") or "").strip()
    )
    audit_updates = _plan_audit_updates(
        repository,
        domain_mapping=domain_mapping,
        user_tenants=user_tenants,
        known_tenants=known_tenants,
    )

    result = MigrationResult(configs=configs)
    if not apply:
        return result

    journal = MigrationJournal.start(repository, mapping=domain_mapping)
    result.run_id = journal.run_id
    try:
        for config in configs:
            journal.create_document(TENANT_COLLECTION, config.tenant_id, _tenant_document(config))
            for domain in config.domains:
                journal.create_document(
                    DOMAIN_COLLECTION,
                    domain,
                    {"domain": domain, "tenantId": config.tenant_id},
                )

        for permission in tenant_permissions:
            key = tenant_permission_key(permission.tenant_id)
            existing = repository.get_document(TOOL_PERMISSION_COLLECTION, key)
            if existing is None:
                if journal.create_document(TOOL_PERMISSION_COLLECTION, key, permission.payload):
                    result.tenant_permissions_created += 1
            elif permission.existing_updates:
                if journal.update_fields(TOOL_PERMISSION_COLLECTION, key, permission.existing_updates):
                    result.tenant_permissions_updated += 1

        for user in user_updates:
            if user.updates and journal.update_fields(AUTH_USER_COLLECTION, user.doc_id, user.updates):
                result.users_updated += 1
            if user.permission_updates and user.email:
                if journal.update_fields(
                    TOOL_PERMISSION_COLLECTION,
                    user.email,
                    user.permission_updates,
                ):
                    result.user_permissions_updated += 1

        for audit in audit_updates:
            if journal.update_fields(AUDIT_COLLECTION, audit.doc_id, {"tenantId": audit.tenant_id}):
                result.audits_updated += 1

        journal.finish(result.summary())
    except Exception as exc:
        journal.fail(exc)
        raise
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate domain-based ownership into first-class tenants")
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="DOMAIN=TENANT_ID",
        help="Explicit domain mapping. Repeat to merge multiple domains into one tenant.",
    )
    parser.add_argument(
        "--require-explicit",
        action="store_true",
        help="Fail if any legacy domain is not listed with --map.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration and record a rollback journal. Default is dry-run.",
    )
    parser.add_argument(
        "--rollback",
        metavar="RUN_ID",
        help="Rollback one prior apply run after drift preflight.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository = get_repository()

    if args.rollback:
        if args.apply or args.map:
            raise SystemExit("--rollback cannot be combined with --apply or --map")
        try:
            summary = rollback_migration(repository, args.rollback)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(
            f"Tenant migration rollback {args.rollback}: "
            f"restored={summary['restored']} deleted={summary['deleted']} "
            f"already_restored={summary['already_restored']}"
        )
        return 0

    try:
        mapping = parse_mapping(args.map)
        result = migrate(
            repository,
            mapping,
            apply=args.apply,
            require_explicit=args.require_explicit,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Tenant migration ({mode}): {len(result.configs)} tenant(s)")
    for config in result.configs:
        print(
            f"  {config.tenant_id}: domains={','.join(config.domains) or '-'} "
            f"storage_namespace={config.storage_namespace}"
        )
    if args.apply:
        print(f"Migration run id: {result.run_id}")
        print(f"Updated local auth users: {result.users_updated}")
        print(f"Created tenant tool permissions: {result.tenant_permissions_created}")
        print(f"Updated tenant tool permissions: {result.tenant_permissions_updated}")
        print(f"Attributed user tool permissions: {result.user_permissions_updated}")
        print(f"Attributed audit rows: {result.audits_updated}")
        print("Firebase/OIDC tenant identity claims must be migrated at the external identity provider.")
        print("Keep the run id; rollback is available with --rollback RUN_ID if no migrated data has drifted.")
    else:
        print("No writes performed. Re-run with --apply after reviewing the plan and taking a database backup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

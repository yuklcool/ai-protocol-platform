#!/usr/bin/env python3
"""Migrate legacy ``clients/{domain}`` records into first-class tenants.

The migration is intentionally conservative:

* default tenant id is the legacy domain, preserving current behavior;
* ``--map domain=tenant_id`` may merge multiple domains into one stable tenant;
* conflicting legacy policy/config values fail fast instead of guessing;
* dry-run is the default; writes require ``--apply``;
* local-JWT ``auth_users`` rows are backfilled with the resolved ``tenantId``
  when writes are enabled, so authentication immediately emits the stable id.

Examples:

  # Preview a zero-behavior-change migration.
  uv run python scripts/migrate_tenants.py

  # Merge two historical domains under one stable tenant id.
  uv run python scripts/migrate_tenants.py \
      --map acme.com=tenant-acme \
      --map acme-energy.example=tenant-acme \
      --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any

from db.persistence import get_repository
from db.repository import Repository
from db.tenants import TenantConfig, TenantDirectory, normalize_domain, normalize_tenant_id


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


def migrate(
    repository: Repository,
    mapping: dict[str, str],
    *,
    apply: bool,
    require_explicit: bool,
) -> tuple[list[TenantConfig], int]:
    rows = repository.query_documents("clients", limit=None)
    plan = build_migration_plan(rows, mapping, require_explicit=require_explicit)
    configs = [plan[key].config() for key in sorted(plan)]

    users_updated = 0
    if apply:
        directory = TenantDirectory(repository)
        for config in configs:
            directory.put(config)

        # Backfill built-in self-host accounts from their authoritative domain.
        # Firebase/OIDC identities should use trusted tenant claims instead.
        for user_row in repository.query_documents("auth_users", limit=None):
            doc_id = str(user_row.get("__id") or "").strip()
            if not doc_id:
                continue
            domain = normalize_domain(str(user_row.get("domain") or ""))
            if not domain:
                continue
            tenant_id = directory.tenant_id_for_domain(domain)
            if not tenant_id:
                continue
            if str(user_row.get("tenantId") or "") == tenant_id:
                continue
            repository.update_document("auth_users", doc_id, {"tenantId": tenant_id})
            users_updated += 1

    return configs, users_updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate domain-based clients into first-class tenants")
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
        help="Write tenants/domain mappings and backfill local auth users. Default is dry-run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        mapping = parse_mapping(args.map)
        repository = get_repository()
        configs, users_updated = migrate(
            repository,
            mapping,
            apply=args.apply,
            require_explicit=args.require_explicit,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Tenant migration ({mode}): {len(configs)} tenant(s)")
    for config in configs:
        print(
            f"  {config.tenant_id}: domains={','.join(config.domains) or '-'} "
            f"storage_namespace={config.storage_namespace}"
        )
    if args.apply:
        print(f"Updated local auth users: {users_updated}")
    else:
        print("No writes performed. Re-run with --apply after reviewing the plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

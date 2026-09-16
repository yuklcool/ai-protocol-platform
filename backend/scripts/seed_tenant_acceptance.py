#!/usr/bin/env python3
"""Seed/cleanup two real self-host tenant identities for HTTP isolation acceptance.

The fixture deliberately gives Tenant A and Tenant B the *same uid*.  This
forces request-time authorization to prove that stable ``tenant_id`` remains a
hard boundary even when an upstream identity subject collides across tenants.

The script is intended to run inside the backend container against the active
Repository (normally PostgreSQL).  It does not mock auth, persistence, object
storage or protocol routes.

Usage:

    TENANT_E2E_PASSWORD_A=... TENANT_E2E_PASSWORD_B=... \
      uv run python scripts/seed_tenant_acceptance.py --run-id ci-123

    uv run python scripts/seed_tenant_acceptance.py --run-id ci-123 --cleanup
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from typing import Any

from auth.admin_roles import TENANT_ADMIN_PREFIX
from auth.local_jwt import create_local_user
from auth.permissions import COLLECTION as TOOL_PERMISSION_COLLECTION
from auth.permissions import tenant_permission_key
from config.effective_models import load_effective_models_config
from db.chat_sessions import create_session_index
from db.models.access import AccessControl
from db.persistence import get_repository
from db.tenants import TenantConfig, TenantDirectory

_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def _run_id(value: str) -> str:
    cleaned = value.strip().casefold()
    if not _RUN_ID_RE.fullmatch(cleaned):
        raise ValueError("run id must match ^[a-z0-9][a-z0-9-]{0,31}$")
    return cleaned


def _user_doc_id(email: str) -> str:
    return hashlib.sha256(email.strip().casefold().encode("utf-8")).hexdigest()


def fixture(run_id: str) -> dict[str, str]:
    prefix = f"tenant-e2e-{run_id}"
    tenant_a = f"{prefix}-a"
    tenant_b = f"{prefix}-b"
    domain_a = f"a-{run_id}.tenant-e2e.invalid"
    domain_b = f"b-{run_id}.tenant-e2e.invalid"
    return {
        "run_id": run_id,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "domain_a": domain_a,
        "domain_b": domain_b,
        "email_a": f"admin@{domain_a}",
        "email_b": f"admin@{domain_b}",
        "shared_uid": f"{prefix}-shared-uid",
        "session_a": f"{prefix}-session-a",
        "session_b": f"{prefix}-session-b",
        "mcp_a": f"{prefix}-mcp-a",
        "mcp_b": f"{prefix}-mcp-b",
        "upload_filename": f"{prefix}.txt",
    }


def _model_pair() -> tuple[str, str | None]:
    config = load_effective_models_config()
    model_ids = [model.id for model in config.models if model.id]
    if not model_ids:
        raise RuntimeError("tenant acceptance requires at least one effective model")
    return model_ids[0], model_ids[1] if len(model_ids) > 1 else None


def _password(name: str) -> str:
    value = os.environ.get(name, "")
    if len(value) < 12:
        raise ValueError(f"{name} must be configured with at least 12 characters")
    return value


def seed(run_id: str) -> dict[str, Any]:
    ids = fixture(run_id)
    password_a = _password("TENANT_E2E_PASSWORD_A")
    password_b = _password("TENANT_E2E_PASSWORD_B")
    model_a, model_b = _model_pair()

    repo = get_repository()
    directory = TenantDirectory(repo)
    for tenant_id in (ids["tenant_a"], ids["tenant_b"]):
        if repo.get_document("tenants", tenant_id) is not None:
            raise ValueError(
                f"acceptance fixture {tenant_id!r} already exists; use a new --run-id or run --cleanup"
            )

    policy_a: dict[str, Any] = {"allowedModels": [model_a], "defaultModel": model_a}
    policy_b: dict[str, Any]
    if model_b:
        policy_b = {"allowedModels": [model_b], "defaultModel": model_b}
    else:
        # A one-model registry can still prove the policy boundary by making B
        # an explicit deny-all tenant.
        policy_b = {"allowedModels": []}

    directory.put(
        TenantConfig(
            tenantId=ids["tenant_a"],
            displayName=f"Tenant acceptance A ({run_id})",
            domains=[ids["domain_a"]],
            modelPolicy=policy_a,
            storageNamespace=ids["tenant_a"],
            quota={"acceptanceBucket": "A"},
        )
    )
    directory.put(
        TenantConfig(
            tenantId=ids["tenant_b"],
            displayName=f"Tenant acceptance B ({run_id})",
            domains=[ids["domain_b"]],
            modelPolicy=policy_b,
            storageNamespace=ids["tenant_b"],
            quota={"acceptanceBucket": "B"},
        )
    )

    # Same uid is intentional.  Email + authoritative auth_users rows still
    # distinguish the two local identities and bind each to a different tenant.
    create_local_user(
        email=ids["email_a"],
        password=password_a,
        uid=ids["shared_uid"],
        tenant_id=ids["tenant_a"],
        group_tags={f"{TENANT_ADMIN_PREFIX}{ids['tenant_a']}"},
    )
    create_local_user(
        email=ids["email_b"],
        password=password_b,
        uid=ids["shared_uid"],
        tenant_id=ids["tenant_b"],
        group_tags={f"{TENANT_ADMIN_PREFIX}{ids['tenant_b']}"},
    )

    repo.set_document(
        TOOL_PERMISSION_COLLECTION,
        tenant_permission_key(ids["tenant_a"]),
        {
            "type": "tenant",
            "tenantId": ids["tenant_a"],
            "tools": ["tenant_e2e_tool_a"],
            "denied": ["tenant_e2e_tool_b"],
        },
    )
    repo.set_document(
        TOOL_PERMISSION_COLLECTION,
        tenant_permission_key(ids["tenant_b"]),
        {
            "type": "tenant",
            "tenantId": ids["tenant_b"],
            "tools": ["tenant_e2e_tool_b"],
            "denied": ["tenant_e2e_tool_a"],
        },
    )

    # Public ACL is deliberate: B must still be denied A's session because the
    # stable tenant boundary is evaluated before/independently of sharing ACLs.
    create_session_index(
        session_id=ids["session_a"],
        skill_id="tenant-e2e",
        owner_uid=ids["shared_uid"],
        owner_domain=ids["domain_a"],
        tenant_id=ids["tenant_a"],
        access_control=AccessControl(type="public"),
    )
    create_session_index(
        session_id=ids["session_b"],
        skill_id="tenant-e2e",
        owner_uid=ids["shared_uid"],
        owner_domain=ids["domain_b"],
        tenant_id=ids["tenant_b"],
        access_control=AccessControl(type="public"),
    )

    return {
        **ids,
        "model_a": model_a,
        "model_b": model_b,
        "policy_b_deny_all": model_b is None,
    }


def _cleanup_documents(repo, ids: dict[str, str]) -> int:
    """Best-effort removal of acceptance uploads left by an interrupted run."""
    removed = 0
    tenant_ids = {ids["tenant_a"], ids["tenant_b"]}
    for raw in repo.query_documents("parsed_documents", limit=None):
        doc_id = str(raw.get("__id") or "")
        if not doc_id or str(raw.get("tenantId") or "") not in tenant_ids:
            continue
        if str(raw.get("originalFilename") or "") != ids["upload_filename"]:
            continue
        key = str(raw.get("storagePath") or "")
        backend = str(raw.get("storageBackend") or "").lower()
        if key and backend == "local":
            try:
                from object_storage import get_object_storage

                get_object_storage().delete(str(raw.get("tenantId") or ""), key)
            except Exception:
                # Cleanup remains metadata-safe and narrowly scoped even when
                # the binary was already deleted through the HTTP endpoint.
                pass
        repo.delete_document("parsed_documents", doc_id)
        removed += 1
    return removed


def cleanup(run_id: str) -> dict[str, Any]:
    ids = fixture(run_id)
    repo = get_repository()
    removed_documents = _cleanup_documents(repo, ids)

    for session_id in (ids["session_a"], ids["session_b"]):
        repo.delete_document("chat_sessions", session_id)
    for server_id in (ids["mcp_a"], ids["mcp_b"]):
        repo.delete_document("mcp_servers", server_id)
    for tenant_id in (ids["tenant_a"], ids["tenant_b"]):
        repo.delete_document(TOOL_PERMISSION_COLLECTION, tenant_permission_key(tenant_id))

    for raw in repo.query_documents("document_folders", limit=None):
        if str(raw.get("tenantId") or "") in {ids["tenant_a"], ids["tenant_b"]}:
            doc_id = str(raw.get("__id") or "")
            if doc_id:
                repo.delete_document("document_folders", doc_id)

    # Remove only audit rows produced by these acceptance identities/resources.
    actor_emails = {ids["email_a"], ids["email_b"]}
    tenant_ids = {ids["tenant_a"], ids["tenant_b"]}
    for raw in repo.query_documents("admin_audit", limit=None):
        if (
            str(raw.get("actorEmail") or "").casefold() in actor_emails
            and str(raw.get("tenantId") or "") in tenant_ids
        ):
            doc_id = str(raw.get("__id") or "")
            if doc_id:
                repo.delete_document("admin_audit", doc_id)

    for email in (ids["email_a"], ids["email_b"]):
        repo.delete_document("auth_users", _user_doc_id(email))
    for domain in (ids["domain_a"], ids["domain_b"]):
        repo.delete_document("tenant_domains", domain)
    for tenant_id in (ids["tenant_a"], ids["tenant_b"]):
        repo.delete_document("tenants", tenant_id)

    return {"run_id": run_id, "cleaned": True, "documents": removed_documents}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed real Tenant A/B self-host acceptance fixtures")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = _run_id(args.run_id)
    result = cleanup(run_id) if args.cleanup else seed(run_id)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Request-local compatibility adapter for the existing group-admin API."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from auth.local_jwt import USER_COLLECTION, _user_doc_id, get_local_user_by_email
from db.persistence import get_repository


class LocalUserDirectory:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def get_user_by_email(self, email: str) -> SimpleNamespace:
        row = get_local_user_by_email(email)
        if row is None:
            raise KeyError("Account not found")
        # Request-local lookup preserves the exact email even when two tenants
        # intentionally share a UID. Never rediscover an account by UID alone.
        self._records[row["uid"]] = row
        return SimpleNamespace(
            uid=row["uid"],
            email=row["email"],
            tenant_id=row.get("tenantId") or row.get("domain") or "",
            custom_claims={"groupTags": row.get("groupTags") or []},
        )

    def list_users(self) -> SimpleNamespace:
        def records():
            for row in get_repository().query_documents(USER_COLLECTION, limit=None):
                yield SimpleNamespace(
                    uid=row["uid"],
                    email=row["email"],
                    tenant_id=row.get("tenantId") or row.get("domain") or "",
                    custom_claims={"groupTags": row.get("groupTags") or []},
                )

        return SimpleNamespace(iterate_all=records)

    def set_custom_user_claims(self, uid: str, claims: dict[str, Any]) -> None:
        row = self._records[uid]
        if "aitana-admin" in (row.get("groupTags") or []) and "aitana-admin" not in (claims.get("groupTags") or []):
            admins = [
                item
                for item in get_repository().query_documents(USER_COLLECTION, limit=None)
                if not item.get("disabled") and "aitana-admin" in (item.get("groupTags") or [])
            ]
            if len(admins) <= 1:
                raise HTTPException(422, "Cannot remove the last enabled platform administrator")
        get_repository().update_document(
            USER_COLLECTION,
            _user_doc_id(row["email"]),
            {"groupTags": claims.get("groupTags") or [], "updatedAt": int(time.time())},
        )

    def revoke_refresh_tokens(self, uid: str) -> None:
        row = self._records[uid]
        get_repository().update_document(
            USER_COLLECTION,
            _user_doc_id(row["email"]),
            {"tokenVersion": int(row.get("tokenVersion", 0)) + 1, "updatedAt": int(time.time())},
        )

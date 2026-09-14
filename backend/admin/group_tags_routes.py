"""Group-tag registry + tag-holders reverse lookup (v6.9.0 / 9.3).

Registry data is stored through the configured persistence Repository so the
same admin surface works with PostgreSQL self-hosting and Firestore cloud mode.
Firebase is still used only for direct-claim user enumeration; that belongs to
the authentication layer rather than persistence.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from admin.audit import record_admin_action
from admin.scope import PlatformScope, Scope
from auth.admin_roles import PLATFORM_ADMIN_TAG, TENANT_ADMIN_PREFIX
from db.models.group_tags import GroupTag
from db.persistence import get_document, query_documents, set_document

log = logging.getLogger(__name__)

COLLECTION = "group_tags"
_CLAIM = "groupTags"
_MEMBERS_SCAN_CAP = 2000

router = APIRouter(prefix="/api/admin/group-tags", tags=["admin-group-tags"])
members_router = APIRouter(prefix="/api/admin/groups", tags=["admin-group-tags"])


def registry_ids() -> set[str]:
    """Return the set of tag ids currently in the registry (best-effort)."""
    try:
        docs = query_documents(COLLECTION)
    except Exception as exc:
        log.warning("group-tags: registry read failed (%s)", type(exc).__name__)
        return set()
    return {str(d.get("__id")) for d in docs if d.get("__id")}


def is_known_tag(tag: str) -> bool:
    if tag == PLATFORM_ADMIN_TAG or tag.startswith(TENANT_ADMIN_PREFIX):
        return True
    ids = registry_ids()
    if not ids:
        log.info("group-tags: registry empty — allowing grant of %r (bootstrap)", tag)
        return True
    return tag in ids


class GroupTagUpsert(BaseModel):
    label: str = ""
    description: str = ""
    grants: list[str] = []
    tenant_scope: str | None = None


@router.get("", response_model=list[GroupTag])
def list_group_tags(scope: PlatformScope) -> list[GroupTag]:
    out: list[GroupTag] = []
    for raw in query_documents(COLLECTION):
        d = dict(raw)
        tag_id = d.pop("__id", "")
        d.pop("id", None)
        try:
            out.append(GroupTag(id=tag_id, **d))
        except Exception as exc:
            log.warning("group-tags: skipping malformed entry %r (%s)", tag_id, type(exc).__name__)
    log.info("admin.group_tags: list by uid=%s count=%d", scope.user.uid, len(out))
    return out


@router.put("/{tag_id}", response_model=GroupTag)
def upsert_group_tag(tag_id: str, body: GroupTagUpsert, scope: PlatformScope) -> GroupTag:
    tag_id = tag_id.strip()
    if not tag_id:
        raise HTTPException(status_code=422, detail="tag id is required")

    existing = get_document(COLLECTION, tag_id)
    entry = GroupTag(
        id=tag_id,
        label=body.label,
        description=body.description,
        grants=body.grants,
        tenant_scope=body.tenant_scope,
        created_by=(existing or {}).get("created_by") or scope.user.uid,
        created_at=(existing or {}).get("created_at") or GroupTag(id=tag_id).created_at,
    )
    data = entry.model_dump()
    data.pop("id", None)
    set_document(COLLECTION, tag_id, data)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        action="upsert_group_tag",
        target=tag_id,
        before=existing,
        after=data,
    )
    log.info("admin.group_tags: upsert id=%s by uid=%s", tag_id, scope.user.uid)
    return entry


def _fb_auth():
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth
    except ImportError as exc:  # pragma: no cover - deployed only
        raise HTTPException(status_code=503, detail="Firebase Admin unavailable") from exc
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()
    return fb_auth


class TagMember(BaseModel):
    email: str
    uid: str


class TagMembers(BaseModel):
    tag: str
    members: list[TagMember]
    scanned: int
    truncated: bool
    note: str


@members_router.get("/{tag}/members", response_model=TagMembers)
def list_tag_members(tag: str, scope: Scope) -> TagMembers:
    fb = _fb_auth()
    members: list[TagMember] = []
    scanned = 0
    truncated = False
    try:
        for rec in fb.list_users().iterate_all():
            scanned += 1
            if scanned > _MEMBERS_SCAN_CAP:
                truncated = True
                break
            claims = getattr(rec, "custom_claims", None) or {}
            raw = claims.get(_CLAIM) or []
            tags = raw if isinstance(raw, (list, tuple, set)) else []
            if tag in tags:
                member_email = getattr(rec, "email", "") or ""
                member_domain = member_email.rsplit("@", 1)[-1].lower() if "@" in member_email else ""
                if not scope.may(member_domain):
                    continue
                members.append(TagMember(email=member_email, uid=rec.uid))
    except HTTPException:
        raise
    except Exception as exc:
        log.error("admin.group_tags: member scan failed for tag=%s (%s)", tag, type(exc).__name__)
        raise HTTPException(status_code=502, detail="Failed to enumerate users") from exc

    note = f"O(users) scan of {scanned} account(s); direct-claim holders only (domain-derived tags excluded)."
    if truncated:
        note += f" TRUNCATED at the {_MEMBERS_SCAN_CAP}-user cap — result is partial."
    log.info(
        "admin.group_tags: members tag=%s holders=%d scanned=%d truncated=%s by uid=%s",
        tag,
        len(members),
        scanned,
        truncated,
        scope.user.uid,
    )
    return TagMembers(tag=tag, members=members, scanned=scanned, truncated=truncated, note=note)


__all__ = ["COLLECTION", "is_known_tag", "members_router", "registry_ids", "router"]

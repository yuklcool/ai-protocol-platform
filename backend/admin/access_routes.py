"""Effective-access dry-run (v6.9.0 / 9.3).

``POST /api/admin/access/check`` answers "what does this user actually see?" —
the union of the three planes that decide access, each annotated with *why*:

  1. **direct**         — tags in the user's signed JWT ``groupTags`` claim
                          (read from the Firebase custom claims).
  2. **domain-derived** — tags the tenant grants to the whole email domain
                          (``clients/{domain}.derived_group_tags``), unioned into
                          the claim at request time by ``firebase_auth``.
  3. **tool-perm**      — the ``tool_permissions`` decision for a named tool,
                          computed by replicating ``permissions.can_use_tool``'s
                          exact user → domain → wildcard lookup order (using the
                          same ``_doc_allows`` evaluator) so the dry-run cannot
                          diverge from enforcement.

Persistence-backed access metadata is read through the configured Repository,
so the same dry-run works for PostgreSQL self-hosting and Firestore cloud mode.
Firebase remains responsible only for direct identity/custom-claim lookup.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from admin.scope import Scope
from auth import User, build_access_context
from auth import permissions as perms
from db.clients import resolve_derived_group_tags
from db.persistence import get_document

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/access", tags=["admin-access"])

_CLAIM = "groupTags"


class AccessCheckRequest(BaseModel):
    email: str
    skill_id: str | None = Field(default=None, alias="skillId")
    tool_name: str | None = Field(default=None, alias="toolName")
    include_skills: bool = Field(default=False, alias="includeSkills")

    model_config = {"populate_by_name": True}


class ProvenancedTag(BaseModel):
    tag: str
    provenances: list[str]


class ToolPermissionCheck(BaseModel):
    tool: str
    allowed: bool
    provenance: str = "tool-perm"
    reason: str


class SkillAccessCheck(BaseModel):
    skill: str
    found: bool
    allowed: bool
    reason: str


class SkillVisibilityRow(BaseModel):
    skill_id: str = Field(alias="skillId")
    slug: str = ""
    label: str = ""
    visible: bool
    reason: str
    access_allowed: bool = Field(alias="accessAllowed")
    tenant_allowed: bool = Field(alias="tenantAllowed")
    admin_bypass: bool = Field(default=False, alias="adminBypass")

    model_config = {"populate_by_name": True}


class SkillVisibilityPlane(BaseModel):
    enabled_skills: list[str] | None = Field(default=None, alias="enabledSkills")
    visible_count: int = Field(default=0, alias="visibleCount")
    total_count: int = Field(default=0, alias="totalCount")
    hidden_by_tenant_filter: list[str] = Field(default_factory=list, alias="hiddenByTenantFilter")
    skills: list[SkillVisibilityRow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class AccessCheckResponse(BaseModel):
    email: str
    uid: str
    domain: str
    user_found: bool
    tags: list[ProvenancedTag]
    tool_permission: ToolPermissionCheck | None = None
    skill_access: SkillAccessCheck | None = None
    skill_visibility: SkillVisibilityPlane | None = Field(default=None, alias="skillVisibility")

    model_config = {"populate_by_name": True}


def _fb_auth():
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth
    except ImportError:  # pragma: no cover - deployed only
        return None
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app()
    return fb_auth


def _direct_tags(email: str) -> tuple[str, list[str], bool]:
    fb = _fb_auth()
    if fb is None:
        return "", [], False
    try:
        rec = fb.get_user_by_email(email)
    except Exception:
        return "", [], False
    claims = getattr(rec, "custom_claims", None) or {}
    raw = claims.get(_CLAIM) or []
    tags = sorted({str(t) for t in raw}) if isinstance(raw, (list, tuple, set)) else []
    return rec.uid, tags, True


def _domain_of(email: str) -> str:
    return email.rsplit("@", 1)[1] if "@" in email else ""


def _explain_tool(email: str, domain: str, tool: str) -> tuple[bool, str]:
    """Replicate enforcement order using fresh configured-persistence reads."""
    user_doc = get_document(perms.COLLECTION, email) if email else None
    if user_doc is not None:
        ok = perms._doc_allows(user_doc, tool)
        return ok, f"user-level rule → {'allow' if ok else 'deny'}"
    if domain:
        domain_doc = get_document(perms.COLLECTION, domain)
        if domain_doc is not None:
            ok = perms._doc_allows(domain_doc, tool)
            return ok, f"domain-level rule ({domain}) → {'allow' if ok else 'deny'}"
    wildcard_doc = get_document(perms.COLLECTION, "*")
    if wildcard_doc is not None:
        ok = perms._doc_allows(wildcard_doc, tool)
        return ok, f"wildcard rule → {'allow' if ok else 'deny'}"
    return False, "no matching rule → deny (default)"


def _check_skill(skill_id: str, uid: str, email: str, domain: str, effective_tags: frozenset[str]) -> SkillAccessCheck:
    from skills.skill_config import get_skill

    skill = get_skill(skill_id)
    if skill is None:
        return SkillAccessCheck(skill=skill_id, found=False, allowed=False, reason="skill not found (resolve by id)")
    synthetic = User(uid=uid or "unknown", email=email, domain=domain, group_tags=effective_tags)
    ctx = build_access_context(synthetic)
    allowed = ctx.can_access(skill)
    ac_type = getattr(skill.access_control, "type", "unknown")
    label = getattr(skill, "display_name", "") or getattr(skill, "name", "") or skill_id
    reason = f"access_control.type={ac_type} → {'allow' if allowed else 'deny'}"
    return SkillAccessCheck(skill=label, found=True, allowed=allowed, reason=reason)


def _skill_visibility(uid: str, email: str, domain: str, effective_tags: frozenset[str]) -> SkillVisibilityPlane:
    from db.clients import get_client_cached
    from skills import skill_config
    from skills.visibility import evaluate_visibility

    synthetic = User(uid=uid or "unknown", email=email, domain=domain, group_tags=effective_tags)
    ctx = build_access_context(synthetic)

    try:
        configs = skill_config.list_skills(limit=200)
    except Exception as exc:
        log.warning("admin.access: skill list failed (%s)", type(exc).__name__)
        return SkillVisibilityPlane(enabled_skills=None, visible_count=0, total_count=0, skills=[])

    client = get_client_cached(domain) if domain else None
    enabled = client.enabled_skills if client is not None else None

    verdicts = evaluate_visibility(configs, ctx, enabled)
    rows = [
        SkillVisibilityRow(
            skillId=v.skill_id,
            slug=v.slug,
            label=v.label or v.slug or v.skill_id,
            visible=v.visible,
            reason=v.reason,
            accessAllowed=v.access_allowed,
            tenantAllowed=v.tenant_allowed,
            adminBypass=v.admin_bypass,
        )
        for v in verdicts
    ]
    hidden_by_tenant = [
        (v.label or v.slug or v.skill_id) for v in verdicts if v.access_allowed and not v.tenant_allowed
    ]
    return SkillVisibilityPlane(
        enabledSkills=list(enabled) if enabled is not None else None,
        visibleCount=sum(1 for v in verdicts if v.visible),
        totalCount=len(verdicts),
        hiddenByTenantFilter=hidden_by_tenant,
        skills=rows,
    )


@router.post("/check", response_model=AccessCheckResponse)
def access_check(body: AccessCheckRequest, scope: Scope) -> AccessCheckResponse:
    email = body.email.strip()
    domain = _domain_of(email)
    scope.assert_may(domain)
    uid, direct, user_found = _direct_tags(email)
    derived = set(resolve_derived_group_tags(domain)) if domain else set()

    direct_set = set(direct)
    provenanced: list[ProvenancedTag] = []
    for tag in sorted(direct_set | derived):
        provs: list[str] = []
        if tag in direct_set:
            provs.append("direct")
        if tag in derived:
            provs.append("domain-derived")
        provenanced.append(ProvenancedTag(tag=tag, provenances=provs))

    tool_perm: ToolPermissionCheck | None = None
    if body.tool_name:
        allowed, reason = _explain_tool(email, domain, body.tool_name)
        tool_perm = ToolPermissionCheck(tool=body.tool_name, allowed=allowed, reason=reason)

    effective_tags = frozenset(direct_set | derived)

    skill_access: SkillAccessCheck | None = None
    if body.skill_id:
        skill_access = _check_skill(body.skill_id, uid, email, domain, effective_tags)

    visibility: SkillVisibilityPlane | None = None
    if body.include_skills:
        visibility = _skill_visibility(uid, email, domain, effective_tags)

    log.info(
        "admin.access: check email=%s tags=%d tool=%s skill=%s by uid=%s",
        email,
        len(provenanced),
        body.tool_name,
        body.skill_id,
        scope.user.uid,
    )
    return AccessCheckResponse(
        email=email,
        uid=uid,
        domain=domain,
        user_found=user_found,
        tags=provenanced,
        tool_permission=tool_perm,
        skill_access=skill_access,
        skill_visibility=visibility,
    )


__all__ = ["router"]

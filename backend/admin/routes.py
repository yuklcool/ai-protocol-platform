"""FastAPI router for /api/admin/* endpoints.

The seed endpoint is gated by `_assert_caller_is_service_account` (Google
ID token + SA email allowlist) — it exists to support Cloud Build deploy hooks
and ops runbooks, never end users.

`GET /whoami` is different by design: it is the *role probe* the frontend uses
to decide whether to show the Admin surface at all, so it answers for any
authenticated user rather than 403-ing.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request  # Depends used inside Annotated[]
from pydantic import BaseModel, Field

from admin import platform_seed
from admin.accounts_routes import router as accounts_router
from admin.auth import _assert_caller_is_service_account
from admin.mcp_servers_routes import router as mcp_servers_router
from admin.model_probe_routes import router as model_probe_router
from admin.model_providers_routes import router as model_providers_router
from admin.model_registry_settings_routes import router as model_registry_settings_router
from admin.scope import resolve_admin_scope
from admin.tenant_model_policy_routes import router as tenant_model_policy_router
from admin.tenant_root_routes import router as tenant_root_router
from admin.usage_routes import router as usage_router
from auth import User, get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(mcp_servers_router)
router.include_router(model_providers_router)
router.include_router(model_probe_router)
router.include_router(model_registry_settings_router)
router.include_router(tenant_model_policy_router)
router.include_router(accounts_router)
router.include_router(usage_router)
router.include_router(tenant_root_router)


class AdminWhoAmI(BaseModel):
    """The caller's resolved admin authority.

    `scope` is one of "platform" | "tenant" | "none". "none" is returned with a
    **200**, not a 403 — the frontend needs to distinguish "you are not an
    admin" (render nothing, quietly) from "something broke" (render an error).
    Probing a data endpoint to infer a role is what made the Admin link
    invisible to tenant admins in the first place; this endpoint exists so the
    role question is asked directly.
    """

    scope: str
    tenant_ids: list[str] = Field(default_factory=list, alias="tenantIds")
    email: str = ""


@router.get("/whoami", response_model=AdminWhoAmI)
def admin_whoami(user: Annotated[User, Depends(get_current_user)]) -> AdminWhoAmI:
    """Report the caller's admin scope. Any authenticated user; never 403."""
    resolved = resolve_admin_scope(user)
    if resolved is None:
        return AdminWhoAmI(scope="none", tenantIds=[], email=user.email or "")
    if resolved.is_platform:
        return AdminWhoAmI(scope="platform", tenantIds=[], email=user.email or "")
    return AdminWhoAmI(scope="tenant", tenantIds=sorted(resolved.tenant_ids or ()), email=user.email or "")


@router.post("/seed-platform-skills")
def seed_platform_skills(request: Request) -> dict[str, Any]:
    """Idempotently seed the default platform-owned skills.

    Hit once per deploy by the Cloud Build seed step. Returns a JSON
    SeedSummary so Cloud Build logs capture what happened.
    """
    _assert_caller_is_service_account(request)
    summary = platform_seed.seed()
    return summary.as_dict()

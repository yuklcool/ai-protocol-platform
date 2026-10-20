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
from pydantic import BaseModel

from admin import platform_seed
from admin.accounts_routes import router as accounts_router
from admin.auth import _assert_caller_is_service_account
from admin.mcp_servers_routes import router as mcp_servers_router
from admin.model_probe_routes import router as model_probe_router
from admin.model_providers_routes import router as model_providers_router
from admin.model_registry_settings_routes import router as model_registry_settings_router
from admin.scope import resolve_admin_scope
from admin.usage_routes import router as usage_router
from auth import User, get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(mcp_servers_router)
router.include_router(model_providers_router)
router.include_router(model_probe_router)
router.include_router(model_registry_settings_router)
router.include_router(accounts_router)
router.include_router(usage_router)


class AdminWhoAmI(BaseModel):
    scope: str
    email: str = ""


@router.get("/whoami", response_model=AdminWhoAmI)
def admin_whoami(user: Annotated[User, Depends(get_current_user)]) -> AdminWhoAmI:
    return AdminWhoAmI(scope="platform" if resolve_admin_scope(user) else "none", email=user.email)


@router.post("/seed-platform-skills")
def seed_platform_skills(request: Request) -> dict[str, Any]:
    """Idempotently seed the default platform-owned skills.

    Hit once per deploy by the Cloud Build seed step. Returns a JSON
    SeedSummary so Cloud Build logs capture what happened.
    """
    _assert_caller_is_service_account(request)
    summary = platform_seed.seed()
    return summary.as_dict()

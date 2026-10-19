"""返回调用者的租户首页配置。管理入口统一为 /api/admin/tenants。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import User, get_current_user

# ---------------------------------------------------------------------------
# Non-admin: the caller's own resolved client config
# ---------------------------------------------------------------------------

me_router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientMeResponse(BaseModel):
    domain: str
    display_name: str = ""
    enabled_skills: list[str] | None = None
    default_skill: str | None = None


@me_router.get("/me", response_model=ClientMeResponse)
def get_my_client(user: Annotated[User, Depends(get_current_user)]) -> ClientMeResponse:
    from db.clients import _user_domain, get_client_cached, resolve_default_skill

    domain = _user_domain(user)
    client = get_client_cached(domain) if domain else None
    return ClientMeResponse(
        domain=domain,
        display_name=client.display_name if client else "",
        enabled_skills=client.enabled_skills if client else None,
        default_skill=resolve_default_skill(user),
    )

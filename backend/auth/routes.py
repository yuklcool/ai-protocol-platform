"""FastAPI routes for the auth module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import User, auth_backend, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LocalLoginRequest(BaseModel):
    email: str
    password: str


class LocalTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


def _user_payload(user: User) -> dict:
    """Provider-neutral identity payload returned to authenticated clients."""
    return {
        "uid": user.uid,
        "email": user.email,
        "domain": user.domain,
        "tenantId": user.tenant_id or user.domain,
        "groupTags": sorted(user.group_tags),
        "authMode": user.auth_mode,
    }


@router.post("/login", response_model=LocalTokenResponse)
def local_login(payload: LocalLoginRequest) -> LocalTokenResponse:
    """Authenticate an account from the built-in self-host identity store."""
    if auth_backend() != "local-jwt":
        raise HTTPException(status_code=404, detail="Built-in login is not enabled")

    from auth.local_jwt import authenticate_credentials, issue_access_token

    user = authenticate_credentials(payload.email, payload.password)
    if user is None:
        # Deliberately generic: do not reveal whether the email exists.
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token, expires_in = issue_access_token(user)
    return LocalTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=_user_payload(user),
    )


@router.get("/whoami")
def whoami(user: User = Depends(get_current_user)) -> dict:  # noqa: B008
    return _user_payload(user)

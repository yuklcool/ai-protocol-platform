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


class OidcExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str
    nonce: str


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


@router.get("/status")
async def auth_status() -> dict:
    """Public provider capabilities without exposing credentials."""
    backend = auth_backend()
    payload: dict = {
        "backend": backend,
        "available": True,
        "capabilities": {
            "passwordLogin": backend == "local-jwt",
            "oidc": backend == "oidc",
        },
    }
    if backend != "oidc":
        return payload

    try:
        from auth.oidc import public_oidc_configuration

        payload["oidc"] = await public_oidc_configuration()
    except Exception:
        # Keep the status endpoint safe for a logged-out browser. Detailed
        # provider/network errors stay in server logs and dedicated diagnostics.
        payload["available"] = False
        payload["error"] = "OIDC configuration or discovery is unavailable"
    return payload


@router.get("/oidc/config")
async def oidc_config() -> dict:
    if auth_backend() != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is not enabled")
    try:
        from auth.oidc import public_oidc_configuration

        return await public_oidc_configuration()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OIDC configuration or discovery is unavailable") from exc


@router.post("/oidc/exchange", response_model=LocalTokenResponse)
async def oidc_exchange(payload: OidcExchangeRequest) -> LocalTokenResponse:
    if auth_backend() != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is not enabled")

    from auth.oidc import exchange_authorization_code

    token, expires_in, user = await exchange_authorization_code(
        code=payload.code,
        code_verifier=payload.code_verifier,
        redirect_uri=payload.redirect_uri,
        nonce=payload.nonce,
    )
    return LocalTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=_user_payload(user),
    )


@router.get("/whoami")
def whoami(user: User = Depends(get_current_user)) -> dict:  # noqa: B008
    return _user_payload(user)

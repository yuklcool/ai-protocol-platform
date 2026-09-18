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


class OidcCallbackRequest(BaseModel):
    code: str
    state: str


class OidcCallbackResponse(LocalTokenResponse):
    return_to: str = "/"


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


@router.get("/oidc/start")
async def oidc_start(return_to: str = "/") -> dict:
    if auth_backend() != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is not enabled")
    import httpx

    from auth.oidc import create_oidc_authorization_request

    try:
        return await create_oidc_authorization_request(return_to=return_to)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="OIDC provider discovery failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OIDC browser login is not configured") from exc


@router.post("/oidc/callback", response_model=OidcCallbackResponse)
async def oidc_callback(payload: OidcCallbackRequest) -> OidcCallbackResponse:
    if auth_backend() != "oidc":
        raise HTTPException(status_code=404, detail="OIDC login is not enabled")

    import httpx
    import jwt

    from auth.oidc import complete_oidc_authorization_code

    try:
        result = await complete_oidc_authorization_code(code=payload.code, state=payload.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="OIDC authorization state is invalid or expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="OIDC identity token validation failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="OIDC provider token exchange failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="OIDC browser login is not configured") from exc

    user = result["user"]
    return OidcCallbackResponse(
        access_token=str(result["access_token"]),
        expires_in=int(result["expires_in"]),
        user=_user_payload(user),
        return_to=str(result["return_to"]),
    )


@router.get("/provider")
async def provider_status() -> dict:
    """Return non-secret capabilities for the configured identity provider."""
    backend = auth_backend()
    if backend == "oidc":
        from auth.oidc import oidc_provider_status

        return await oidc_provider_status()
    if backend == "local-jwt":
        return {
            "backend": backend,
            "configured": True,
            "capabilities": {
                "passwordLogin": True,
                "bearerVerification": True,
                "authorizationCodePkce": False,
            },
        }
    return {
        "backend": backend,
        "configured": True,
        "capabilities": {"bearerVerification": backend == "firebase"},
    }


@router.get("/whoami")
def whoami(user: User = Depends(get_current_user)) -> dict:  # noqa: B008
    return _user_payload(user)

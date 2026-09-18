"""Real Keycloak compatibility acceptance for the generic OIDC adapter."""

from __future__ import annotations

import asyncio
import os

import httpx

from auth.local_jwt import create_local_user
from auth.oidc import decode_oidc_token, link_oidc_subject, user_from_oidc_token
from db.persistence import reset_repository_for_testing
from db.repositories.memory import MemoryRepository

ISSUER = os.environ.get(
    "OIDC_ISSUER",
    "http://keycloak:8080/realms/ai-protocol-platform",
).rstrip("/")
CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "ai-protocol-platform")
USERNAME = os.environ.get("KEYCLOAK_TEST_USERNAME", "oidc-admin")
PASSWORD = os.environ.get("KEYCLOAK_TEST_PASSWORD", "oidc-demo-password")
LOCAL_EMAIL = os.environ.get("KEYCLOAK_TEST_EMAIL", "owner@example.com")
TENANT_ID = os.environ.get("KEYCLOAK_TEST_TENANT", "tenant-keycloak")


async def main() -> None:
    os.environ["AUTH_BACKEND"] = "oidc"
    os.environ["OIDC_ISSUER"] = ISSUER
    os.environ["OIDC_CLIENT_ID"] = CLIENT_ID
    os.environ["OIDC_AUDIENCE"] = CLIENT_ID
    os.environ["OIDC_ALLOWED_ALGORITHMS"] = "RS256"

    reset_repository_for_testing(MemoryRepository())
    local = create_local_user(
        email=LOCAL_EMAIL,
        password="compatibility-only-local-password",
        tenant_id=TENANT_ID,
        group_tags={f"tenant-admin:{TENANT_ID}"},
    )

    discovery_url = f"{ISSUER}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=20.0) as client:
        discovery = (await client.get(discovery_url)).raise_for_status().json()
        token_endpoint = discovery["token_endpoint"]
        token_response = await client.post(
            token_endpoint,
            data={
                "grant_type": "password",
                "client_id": CLIENT_ID,
                "username": USERNAME,
                "password": PASSWORD,
                "scope": "openid profile email",
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_payload = token_response.json()

    id_token = str(token_payload.get("id_token") or "")
    if not id_token:
        raise RuntimeError("Keycloak did not return an id_token")

    claims = await decode_oidc_token(id_token)
    subject = str(claims.get("sub") or "")
    if not subject:
        raise RuntimeError("Keycloak id_token did not contain sub")

    link_oidc_subject(issuer=ISSUER, subject=subject, email=LOCAL_EMAIL)
    resolved = await user_from_oidc_token(id_token)

    assert resolved.uid == local.uid
    assert resolved.email == LOCAL_EMAIL
    assert resolved.tenant_id == TENANT_ID
    assert resolved.group_tags == frozenset({f"tenant-admin:{TENANT_ID}"})
    assert resolved.auth_mode == "oidc"

    print("Keycloak OIDC compatibility acceptance OK")
    print(f"issuer={ISSUER}")
    print(f"subject={subject}")
    print(f"tenant={resolved.tenant_id}")


if __name__ == "__main__":
    asyncio.run(main())

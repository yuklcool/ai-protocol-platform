# Optional OIDC identity provider

The default self-host authentication backend remains `local-jwt`. OIDC is an
optional enterprise identity source for deployments using Keycloak, Authentik,
Dex, Entra ID, Okta, or another standards-compliant provider.

## Current baseline

This implementation phase supports:

- OIDC discovery through `/.well-known/openid-configuration`
- JWKS fetch and short-lived in-process caching
- issuer, audience, expiry, issued-at and algorithm verification
- explicit external `issuer + sub` to local user mapping
- server-authoritative tenant/domain/group roles from PostgreSQL `auth_users`
- provider capability/status at `GET /api/auth/provider`
- unified authenticated requests through the existing `get_current_user` seam

Authorization Code + PKCE, browser callback handling, nonce validation, frontend
sign-in/sign-out, and Keycloak example Compose are intentionally left for the
next phase of issue #17.

## Configuration

Set:

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://id.example.com/realms/platform
OIDC_CLIENT_ID=ai-protocol-platform
OIDC_AUDIENCE=ai-protocol-platform
OIDC_ALLOWED_ALGORITHMS=RS256
# Optional override:
# OIDC_DISCOVERY_URL=https://id.example.com/realms/platform/.well-known/openid-configuration
```

`OIDC_AUDIENCE` defaults to `OIDC_CLIENT_ID`. The default accepted signing
algorithm is `RS256`; `none` can never be enabled.

## Link an identity

OIDC does not auto-provision tenant or role data. First create the platform user
using the normal self-host user administration path, then link the IdP subject:

```bash
cd backend
uv run python scripts/link_oidc_subject.py \
  --issuer https://id.example.com/realms/platform \
  --subject 8f927a6b-1234-5678-90ab-example \
  --email owner@example.com
```

The mapping stores the IdP issuer/subject and the local UID/email. Authentication
fails closed if the mapping is missing, the local account is disabled, or the
local UID has changed.

## Authorization boundary

Claims such as these are not trusted for authorization:

```json
{
  "tenant_id": "tenant-a",
  "groupTags": ["aitana-admin"],
  "role": "admin"
}
```

After cryptographic token verification the backend uses only `iss + sub` to
resolve the explicit mapping, reloads the local `auth_users` row, and builds the
same provider-neutral `User / AccessContext` used by local-jwt and Firebase.

This means the identity provider authenticates the caller, while PostgreSQL
remains the authorization source of truth.

## Provider status

```http
GET /api/auth/provider
```

The response intentionally contains only non-secret configuration/capabilities.
When discovery is reachable it also reports the authorization, token, and JWKS
endpoints advertised by the provider.

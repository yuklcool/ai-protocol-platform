# Optional OIDC identity provider

The default self-host authentication backend remains `local-jwt`. OIDC is an
optional enterprise identity source for deployments using Keycloak, Authentik,
Dex, Entra ID, Okta, or another standards-compliant provider.

## Supported flow

The platform supports:

- OIDC discovery through `/.well-known/openid-configuration`
- JWKS fetch and short-lived in-process caching
- issuer, audience, expiry, issued-at and signing-algorithm verification
- browser Authorization Code + PKCE
- server-generated and server-stored state, nonce and PKCE verifier
- one-time state consumption to prevent replay
- nonce validation on the returned ID token
- public PKCE clients and optional confidential-client authentication
- explicit external `issuer + sub` to local user mapping
- server-authoritative tenant/domain/group roles from PostgreSQL `auth_users`
- frontend sign-in, callback, session restore and sign-out
- provider capability/status at `GET /api/auth/provider`
- unified authenticated requests through the existing `get_current_user` seam

The backend performs the code exchange. The browser does not need direct CORS
access to the identity provider's token endpoint and never receives the PKCE
verifier or client secret.

## Configuration

Set:

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://id.example.com/realms/platform
OIDC_CLIENT_ID=ai-protocol-platform
OIDC_AUDIENCE=ai-protocol-platform
OIDC_ALLOWED_ALGORITHMS=RS256
OIDC_REDIRECT_URI=https://platform.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_TRANSACTION_TTL_SECONDS=300
```

`OIDC_AUDIENCE` defaults to `OIDC_CLIENT_ID`. The browser PKCE flow requires
those values to match because the verified ID token is the browser session
credential. The default accepted signing algorithm is `RS256`; `none` can never
be enabled. `OIDC_SCOPES` must include `openid`.

For a public client:

```env
OIDC_CLIENT_AUTH_METHOD=none
```

For a confidential client, use the method required by the provider:

```env
OIDC_CLIENT_AUTH_METHOD=client_secret_basic
OIDC_CLIENT_SECRET=replace-with-secret
```

or:

```env
OIDC_CLIENT_AUTH_METHOD=client_secret_post
OIDC_CLIENT_SECRET=replace-with-secret
```

`OIDC_CLIENT_SECRET` stays server-side and is never returned from
`/api/auth/provider`.

## Browser flow

```text
Browser
  |
  | GET /api/auth/oidc/start
  v
FastAPI
  | generate state + nonce + PKCE verifier
  | persist one-time transaction in platform Repository
  v
OIDC authorization endpoint
  |
  | redirect code + state
  v
/auth/oidc/callback
  |
  | POST code + state to FastAPI
  v
FastAPI
  | consume state once
  | exchange code + verifier at token endpoint
  | verify ID token signature / issuer / audience / nonce
  | resolve issuer + sub mapping
  | reload tenant/roles from auth_users
  v
Browser sessionStorage
  |
  | Authorization: Bearer <verified ID token>
  v
Existing get_current_user boundary
```

The callback stores the verified ID token in browser `sessionStorage`, matching
the existing local-jwt browser-session lifetime model. Closing the tab drops the
browser session. When the ID token expires, the user signs in again.

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
When discovery is reachable it reports the authorization, token, logout and JWKS
endpoints advertised by the provider, along with the configured redirect URI,
scopes and non-secret client-auth method.

## Remaining #17 work

The generic browser flow is provider-neutral. Issue #17 still remains open until
the repository also contains provider-specific examples and real compatibility
acceptance, including a Keycloak example and optional Entra ID / Okta setup
notes.


## Provider-specific examples

See [OIDC provider examples](oidc-providers.md) for:

- the optional real Keycloak Compose/realm example
- Microsoft Entra ID configuration
- Okta configuration
- the real Keycloak compatibility CI gate

Keycloak remains opt-in and is not part of the default Self-host Compose.

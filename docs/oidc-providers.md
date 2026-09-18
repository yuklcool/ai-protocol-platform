# OIDC provider examples

The platform's generic OIDC adapter is provider-neutral. These examples show
how to point it at common identity providers without changing the default
`AUTH_BACKEND=local-jwt` self-host profile.

Authorization remains local and server-authoritative: external claims do not
create tenants, platform admins, or tenant-admin roles. Link each external
`issuer + sub` to an existing local `auth_users` account.

## Keycloak

A development-only Keycloak example is included in:

```text
docker-compose.keycloak.yml
examples/oidc/keycloak/realm-export.json
```

The example pins Keycloak 26.7.4 and imports:

- realm: `ai-protocol-platform`
- public client: `ai-protocol-platform`
- Authorization Code + PKCE S256
- redirect URI: `http://localhost:3456/auth/oidc/callback`
- demo user: `oidc-admin` / `owner@example.com`

Start only the optional IdP:

```bash
docker compose -f docker-compose.keycloak.yml up -d
```

The default application Compose is unchanged; Keycloak is never started unless
this extra Compose file is explicitly selected.

For a real deployment use HTTPS and a DNS name reachable by both browser and
backend, then configure:

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://sso.example.com/realms/ai-protocol-platform
OIDC_CLIENT_ID=ai-protocol-platform
OIDC_AUDIENCE=ai-protocol-platform
OIDC_REDIRECT_URI=https://platform.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_CLIENT_AUTH_METHOD=none
```

For a confidential Keycloak client, configure a client secret and use
`client_secret_basic` (preferred when supported) or `client_secret_post`.

## Microsoft Entra ID

Create an App Registration with a Web redirect URI matching the platform
callback. For a single-tenant application use the tenant-specific v2 issuer:

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_CLIENT_ID=<application-client-id>
OIDC_AUDIENCE=<application-client-id>
OIDC_REDIRECT_URI=https://platform.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_CLIENT_AUTH_METHOD=client_secret_post
OIDC_CLIENT_SECRET=<secret-reference-value>
```

Use a tenant-specific issuer rather than `common` when the deployment expects
one enterprise tenant. The platform still maps the verified external `sub` to
its own local user/tenant record.

## Okta

Create an OIDC Web Application and register the platform callback URL. For an
Okta custom authorization server, a common issuer form is:

```env
AUTH_BACKEND=oidc
OIDC_ISSUER=https://<your-okta-domain>/oauth2/default
OIDC_CLIENT_ID=<client-id>
OIDC_AUDIENCE=<client-id>
OIDC_REDIRECT_URI=https://platform.example.com/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_CLIENT_AUTH_METHOD=client_secret_basic
OIDC_CLIENT_SECRET=<secret-reference-value>
```

If your Okta authorization server uses a different issuer, copy the exact
`issuer` value from its discovery document; issuer comparison is exact after
normalizing only the trailing slash.

## Linking users

After the user exists in the platform's local identity store, link the verified
external subject:

```bash
cd backend
uv run python scripts/link_oidc_subject.py \
  --issuer https://sso.example.com/realms/ai-protocol-platform \
  --subject <external-sub> \
  --email owner@example.com
```

The external email claim is not used as an authorization shortcut. A subject
must be explicitly linked before authentication succeeds.

## Compatibility gate

The repository includes a real Keycloak compatibility workflow:

```text
.github/workflows/oidc-keycloak-compatibility.yml
```

It starts Keycloak, imports the example realm, obtains a genuinely signed
Keycloak ID token, and validates the platform's real discovery, JWKS, issuer,
audience, signature, subject mapping, and server-authoritative tenant/role
reload path.

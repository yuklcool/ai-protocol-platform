#!/usr/bin/env bash
# Real self-host Tenant A/B isolation acceptance (no external LLM required).
#
# This script talks to a running backend over HTTP while fixture setup uses the
# backend container's active Repository (normally PostgreSQL).  It intentionally
# creates two local-jwt users with the SAME uid but different stable tenant ids.
# Passing therefore proves tenant scope, not uid uniqueness, is the hard wall.
#
# Preconditions:
#   docker compose up -d postgres backend
#
# LLM-dependent acceptance (quota consumption and a real tool invocation) is
# deliberately NOT claimed here; that remains part of the real Provider E2E.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:1956}"
RUN_ID="${TENANT_E2E_RUN_ID:-$(date +%s)-$RANDOM}"
RUN_ID="$(printf '%s' "$RUN_ID" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-32)"
PASSWORD_A="${TENANT_E2E_PASSWORD_A:-tenant-e2e-a-${RUN_ID}-password}"
PASSWORD_B="${TENANT_E2E_PASSWORD_B:-tenant-e2e-b-${RUN_ID}-password}"

if [ -z "$RUN_ID" ]; then
  echo "ERROR: TENANT_E2E_RUN_ID normalized to an empty value" >&2
  exit 1
fi
for cmd in curl python3 docker; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd is required" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d)"
SEEDED=0
TOKEN_A=""
TOKEN_B=""
DOC_A=""
DOC_B=""

ok() { printf '✓ %s\n' "$1"; }
fail() { printf '✗ %s\n' "$1" >&2; exit 1; }

json_value() {
  local key="$1"
  python3 -c 'import json,sys; v=json.load(sys.stdin).get(sys.argv[1]); print("" if v is None else ("true" if v is True else "false" if v is False else v))' "$key"
}

http_code() {
  local method="$1" url="$2" token="$3" output="$4"
  shift 4
  curl -sS -o "$output" -w '%{http_code}' -X "$method" \
    -H "Authorization: Bearer $token" "$@" "$url"
}

expect_code() {
  local name="$1" expected="$2" method="$3" url="$4" token="$5"
  shift 5
  local output="$TMP_DIR/response-$(date +%s%N).json" code
  code="$(http_code "$method" "$url" "$token" "$output" "$@")"
  if [ "$code" != "$expected" ]; then
    echo "Response body:" >&2
    cat "$output" >&2 || true
    fail "$name returned HTTP $code; expected $expected"
  fi
  ok "$name"
}

cleanup() {
  set +e
  if [ -n "$DOC_A" ] && [ -n "$TOKEN_A" ]; then
    curl -sS -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN_A" "$BACKEND_URL/api/documents/$DOC_A" || true
  fi
  if [ -n "$DOC_B" ] && [ -n "$TOKEN_B" ]; then
    curl -sS -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN_B" "$BACKEND_URL/api/documents/$DOC_B" || true
  fi
  if [ "$SEEDED" = "1" ]; then
    docker compose exec -T backend \
      uv run python scripts/seed_tenant_acceptance.py --run-id "$RUN_ID" --cleanup >/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

printf '\nAI Protocol Platform — real Tenant A/B self-host isolation acceptance\n'
printf 'Backend: %s\nRun id: %s\n\n' "$BACKEND_URL" "$RUN_ID"

curl -fsS --max-time 10 "$BACKEND_URL/health" >/dev/null || fail "backend health is unavailable"
ok "Backend health"

SEED_JSON="$(
  docker compose exec -T \
    -e "TENANT_E2E_PASSWORD_A=$PASSWORD_A" \
    -e "TENANT_E2E_PASSWORD_B=$PASSWORD_B" \
    backend uv run python scripts/seed_tenant_acceptance.py --run-id "$RUN_ID" \
    | tail -n 1
)"
SEEDED=1
printf '%s' "$SEED_JSON" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null || fail "fixture seeder did not return JSON"
ok "PostgreSQL tenant fixtures seeded"

TENANT_A="$(printf '%s' "$SEED_JSON" | json_value tenant_a)"
TENANT_B="$(printf '%s' "$SEED_JSON" | json_value tenant_b)"
DOMAIN_A="$(printf '%s' "$SEED_JSON" | json_value domain_a)"
DOMAIN_B="$(printf '%s' "$SEED_JSON" | json_value domain_b)"
EMAIL_A="$(printf '%s' "$SEED_JSON" | json_value email_a)"
EMAIL_B="$(printf '%s' "$SEED_JSON" | json_value email_b)"
SESSION_A="$(printf '%s' "$SEED_JSON" | json_value session_a)"
SESSION_B="$(printf '%s' "$SEED_JSON" | json_value session_b)"
MCP_A="$(printf '%s' "$SEED_JSON" | json_value mcp_a)"
MCP_B="$(printf '%s' "$SEED_JSON" | json_value mcp_b)"
UPLOAD_FILENAME="$(printf '%s' "$SEED_JSON" | json_value upload_filename)"
MODEL_A="$(printf '%s' "$SEED_JSON" | json_value model_a)"
MODEL_B="$(printf '%s' "$SEED_JSON" | json_value model_b)"
DENY_ALL_B="$(printf '%s' "$SEED_JSON" | json_value policy_b_deny_all)"

login() {
  local email="$1" password="$2"
  python3 -c 'import json,sys; print(json.dumps({"email":sys.argv[1],"password":sys.argv[2]}))' "$email" "$password" \
    | curl -fsS -H 'content-type: application/json' --data-binary @- "$BACKEND_URL/api/auth/login"
}

LOGIN_A="$(login "$EMAIL_A" "$PASSWORD_A")"
LOGIN_B="$(login "$EMAIL_B" "$PASSWORD_B")"
TOKEN_A="$(printf '%s' "$LOGIN_A" | json_value access_token)"
TOKEN_B="$(printf '%s' "$LOGIN_B" | json_value access_token)"
[ -n "$TOKEN_A" ] && [ -n "$TOKEN_B" ] || fail "local-jwt login did not return both tokens"
ok "Tenant A/B local-jwt login"

curl -fsS -H "Authorization: Bearer $TOKEN_A" "$BACKEND_URL/api/auth/whoami" > "$TMP_DIR/whoami-a.json"
curl -fsS -H "Authorization: Bearer $TOKEN_B" "$BACKEND_URL/api/auth/whoami" > "$TMP_DIR/whoami-b.json"
python3 - "$TENANT_A" "$TENANT_B" "$TMP_DIR/whoami-a.json" "$TMP_DIR/whoami-b.json" <<'PY'
import json,sys
expected_a, expected_b, path_a, path_b = sys.argv[1:]
a=json.load(open(path_a)); b=json.load(open(path_b))
assert a['tenantId']==expected_a, a
assert b['tenantId']==expected_b, b
assert a['uid']==b['uid'], (a,b)  # deliberately same subject
assert a['tenantId']!=b['tenantId']
PY
ok "Trusted identity keeps same uid partitioned by stable tenant"

# First-class tenant admin scope.
expect_code "Tenant A validates own tenant" 200 GET "$BACKEND_URL/api/admin/tenants/$TENANT_A/validate" "$TOKEN_A"
expect_code "Tenant A cannot validate Tenant B" 403 GET "$BACKEND_URL/api/admin/tenants/$TENANT_B/validate" "$TOKEN_A"
expect_code "Tenant B validates own tenant" 200 GET "$BACKEND_URL/api/admin/tenants/$TENANT_B/validate" "$TOKEN_B"
expect_code "Tenant B cannot validate Tenant A" 403 GET "$BACKEND_URL/api/admin/tenants/$TENANT_A/validate" "$TOKEN_B"

# Public session ACL must still not cross the tenant wall, even with the same uid.
expect_code "Tenant A reads own public session" 200 GET "$BACKEND_URL/api/sessions/$SESSION_A" "$TOKEN_A"
expect_code "Tenant B is denied Tenant A public session" 403 GET "$BACKEND_URL/api/sessions/$SESSION_A" "$TOKEN_B"
expect_code "Tenant B reads own public session" 200 GET "$BACKEND_URL/api/sessions/$SESSION_B" "$TOKEN_B"
expect_code "Tenant A is denied Tenant B public session" 403 GET "$BACKEND_URL/api/sessions/$SESSION_B" "$TOKEN_A"

curl -fsS -H "Authorization: Bearer $TOKEN_A" "$BACKEND_URL/api/sessions" > "$TMP_DIR/sessions-a.json"
curl -fsS -H "Authorization: Bearer $TOKEN_B" "$BACKEND_URL/api/sessions" > "$TMP_DIR/sessions-b.json"
python3 - "$SESSION_A" "$SESSION_B" "$TMP_DIR/sessions-a.json" "$TMP_DIR/sessions-b.json" <<'PY'
import json,sys
sa,sb,pa,pb=sys.argv[1:]
a={row['session_id'] for row in json.load(open(pa))['sessions']}
b={row['session_id'] for row in json.load(open(pb))['sessions']}
assert sa in a and sb not in a, (a,sa,sb)
assert sb in b and sa not in b, (b,sa,sb)
PY
ok "Session list is tenant-partitioned despite shared uid"

# Real local ObjectStorage upload/read isolation. Same filename + same uid on
# both tenants stresses tenant namespace separation rather than path uniqueness.
printf 'Tenant A isolated payload for %s\n' "$RUN_ID" > "$TMP_DIR/$UPLOAD_FILENAME"
UPLOAD_A="$(curl -fsS -H "Authorization: Bearer $TOKEN_A" -F "file=@$TMP_DIR/$UPLOAD_FILENAME;type=text/plain" "$BACKEND_URL/api/documents/upload")"
DOC_A="$(printf '%s' "$UPLOAD_A" | json_value docId)"
[ -n "$DOC_A" ] || fail "Tenant A upload did not return docId"
expect_code "Tenant A reads own uploaded document" 200 GET "$BACKEND_URL/api/documents/$DOC_A" "$TOKEN_A"
expect_code "Tenant B is denied Tenant A document with same uid" 403 GET "$BACKEND_URL/api/documents/$DOC_A" "$TOKEN_B"

printf 'Tenant B isolated payload for %s\n' "$RUN_ID" > "$TMP_DIR/$UPLOAD_FILENAME"
UPLOAD_B="$(curl -fsS -H "Authorization: Bearer $TOKEN_B" -F "file=@$TMP_DIR/$UPLOAD_FILENAME;type=text/plain" "$BACKEND_URL/api/documents/upload")"
DOC_B="$(printf '%s' "$UPLOAD_B" | json_value docId)"
[ -n "$DOC_B" ] || fail "Tenant B upload did not return docId"
[ "$DOC_A" != "$DOC_B" ] || fail "Tenant A/B uploads unexpectedly resolved to the same document id"
expect_code "Tenant B reads own uploaded document" 200 GET "$BACKEND_URL/api/documents/$DOC_B" "$TOKEN_B"
expect_code "Tenant A is denied Tenant B document with same uid" 403 GET "$BACKEND_URL/api/documents/$DOC_B" "$TOKEN_A"
ok "Local ObjectStorage document namespace is tenant-safe"

# Tenant model metadata is filtered by the first-class model policy.
curl -fsS -H "Authorization: Bearer $TOKEN_A" "$BACKEND_URL/api/models" > "$TMP_DIR/models-a.json"
curl -fsS -H "Authorization: Bearer $TOKEN_B" "$BACKEND_URL/api/models" > "$TMP_DIR/models-b.json"
python3 - "$MODEL_A" "$MODEL_B" "$DENY_ALL_B" "$TMP_DIR/models-a.json" "$TMP_DIR/models-b.json" <<'PY'
import json,sys
ma,mb,deny,pa,pb=sys.argv[1:]
a=json.load(open(pa)); b=json.load(open(pb))
ids_a=[row['id'] for row in a['models']]
ids_b=[row['id'] for row in b['models']]
assert ids_a == [ma], (ids_a,ma)
assert a['platform_default'] == ma, a
if deny == 'true':
    assert ids_b == [], ids_b
    assert b['platform_default'] == '', b
else:
    assert ids_b == [mb], (ids_b,mb)
    assert b['platform_default'] == mb, b
assert ma not in ids_b
if mb:
    assert mb not in ids_a
PY
ok "Tenant Model Policy filters authenticated /api/models"

# Stable tenant Tool Permission documents are scoped to the matching tenant admin.
PERM_A="tenant:$TENANT_A"
PERM_B="tenant:$TENANT_B"
expect_code "Tenant A reads own stable tool permission" 200 GET "$BACKEND_URL/api/admin/tool-permissions/$PERM_A" "$TOKEN_A"
expect_code "Tenant A cannot read Tenant B tool permission" 403 GET "$BACKEND_URL/api/admin/tool-permissions/$PERM_B" "$TOKEN_A"
expect_code "Tenant B reads own stable tool permission" 200 GET "$BACKEND_URL/api/admin/tool-permissions/$PERM_B" "$TOKEN_B"
expect_code "Tenant B cannot read Tenant A tool permission" 403 GET "$BACKEND_URL/api/admin/tool-permissions/$PERM_A" "$TOKEN_B"

# MCP Admin: each tenant can create its own server, but another tenant gets a
# 404 to avoid leaking endpoint existence.
MCP_BODY_A="$(python3 -c 'import json,sys; print(json.dumps({"url":sys.argv[1],"transport":"http","scope":"tenant","enabled":True,"description":"tenant live acceptance A"}))' "http://mcp-a-$RUN_ID.invalid/mcp")"
MCP_BODY_B="$(python3 -c 'import json,sys; print(json.dumps({"url":sys.argv[1],"transport":"http","scope":"tenant","enabled":True,"description":"tenant live acceptance B"}))' "http://mcp-b-$RUN_ID.invalid/mcp")"
expect_code "Tenant A creates own MCP config" 200 PUT "$BACKEND_URL/api/admin/mcp-servers/$MCP_A" "$TOKEN_A" -H 'content-type: application/json' --data-binary "$MCP_BODY_A"
expect_code "Tenant B cannot discover Tenant A MCP config" 404 GET "$BACKEND_URL/api/admin/mcp-servers/$MCP_A" "$TOKEN_B"
expect_code "Tenant B creates own MCP config" 200 PUT "$BACKEND_URL/api/admin/mcp-servers/$MCP_B" "$TOKEN_B" -H 'content-type: application/json' --data-binary "$MCP_BODY_B"
expect_code "Tenant A cannot discover Tenant B MCP config" 404 GET "$BACKEND_URL/api/admin/mcp-servers/$MCP_B" "$TOKEN_A"

curl -fsS -H "Authorization: Bearer $TOKEN_A" "$BACKEND_URL/api/admin/mcp-servers" > "$TMP_DIR/mcp-a.json"
curl -fsS -H "Authorization: Bearer $TOKEN_B" "$BACKEND_URL/api/admin/mcp-servers" > "$TMP_DIR/mcp-b.json"
python3 - "$MCP_A" "$MCP_B" "$TMP_DIR/mcp-a.json" "$TMP_DIR/mcp-b.json" <<'PY'
import json,sys
ma,mb,pa,pb=sys.argv[1:]
a={row['server_id'] for row in json.load(open(pa))}
b={row['server_id'] for row in json.load(open(pb))}
assert ma in a and mb not in a, (a,ma,mb)
assert mb in b and ma not in b, (b,ma,mb)
PY
ok "MCP Admin list hides other tenant private configs"

# The MCP writes above produce real audit rows; tenant admins must only see the
# row attributed to their own stable tenant.
curl -fsS -H "Authorization: Bearer $TOKEN_A" "$BACKEND_URL/api/admin/audit?action=upsert_mcp_server" > "$TMP_DIR/audit-a.json"
curl -fsS -H "Authorization: Bearer $TOKEN_B" "$BACKEND_URL/api/admin/audit?action=upsert_mcp_server" > "$TMP_DIR/audit-b.json"
python3 - "$TENANT_A" "$TENANT_B" "$MCP_A" "$MCP_B" "$TMP_DIR/audit-a.json" "$TMP_DIR/audit-b.json" <<'PY'
import json,sys
ta,tb,ma,mb,pa,pb=sys.argv[1:]
a=json.load(open(pa))['entries']; b=json.load(open(pb))['entries']
assert any(row['target']==ma and row['tenantId']==ta for row in a), a
assert all(row['tenantId']==ta for row in a), a
assert all(row['target']!=mb for row in a), a
assert any(row['target']==mb and row['tenantId']==tb for row in b), b
assert all(row['tenantId']==tb for row in b), b
assert all(row['target']!=ma for row in b), b
PY
ok "Admin Audit read/count boundary is tenant-scoped"

printf '\nReal non-LLM Tenant A/B acceptance passed.\n'
printf 'Covered: local-jwt identity, Tenant Admin scope, Session, local document storage, Model Policy, Tool Permission admin scope, MCP config, Audit.\n'
printf 'Still requires a real model/provider: quota consumption boundary and actual Agent Tool Calling.\n'

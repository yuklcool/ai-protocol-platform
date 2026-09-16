#!/usr/bin/env bash
# Real self-host MCP acceptance against the Compose example server.
#
# Covers the non-LLM portion of Issue #11:
#   Admin register -> initialize health -> discovery -> Skill binding ->
#   authenticated /mcp proxy -> tools/list -> MCP Apps resources/read.
#
# The final Agent-selected Tool Call and browser iframe rendering still require
# a real model/browser acceptance and are intentionally not claimed here.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:1956}"
ADMIN_EMAIL="${SELFHOST_ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${SELFHOST_ADMIN_PASSWORD:-}"
RUN_ID="${MCP_E2E_RUN_ID:-$(date +%s)-$RANDOM}"
RUN_ID="$(printf '%s' "$RUN_ID" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-24)"
SERVER_ID="mcp-live-${RUN_ID}"
UPSTREAM_URL="http://mcp-example-map:8080/mcp"

[ -n "$ADMIN_PASSWORD" ] || { echo "ERROR: SELFHOST_ADMIN_PASSWORD is required" >&2; exit 1; }
[ -n "$RUN_ID" ] || { echo "ERROR: MCP_E2E_RUN_ID normalized to empty" >&2; exit 1; }
for cmd in curl python3 docker; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd is required" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d)"
TOKEN=""
SKILL_ID=""
SERVER_CREATED=0

ok() { printf '✓ %s\n' "$1"; }
fail() { printf '✗ %s\n' "$1" >&2; exit 1; }

json_value() {
  local expression="$1"
  python3 -c 'import json,sys; d=json.load(sys.stdin); v=eval(sys.argv[1], {"__builtins__":{}}, {"d":d}); print("" if v is None else v)' "$expression"
}

cleanup() {
  set +e
  if [ -n "$TOKEN" ] && [ -n "$SKILL_ID" ]; then
    curl -sS -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN" \
      "$BACKEND_URL/api/skills/$SKILL_ID" || true
  fi
  if [ -n "$TOKEN" ] && [ "$SERVER_CREATED" = "1" ]; then
    curl -sS -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN" \
      "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID" || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

printf '\nAI Protocol Platform — real Self-host MCP acceptance\n'
printf 'Backend: %s\nServer id: %s\nUpstream: %s\n\n' "$BACKEND_URL" "$SERVER_ID" "$UPSTREAM_URL"

curl -fsS --max-time 10 "$BACKEND_URL/health" >/dev/null || fail "backend health unavailable"
ok "Backend health"

LOGIN_PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({"email":sys.argv[1],"password":sys.argv[2]}))' "$ADMIN_EMAIL" "$ADMIN_PASSWORD")"
LOGIN="$(curl -fsS -H 'content-type: application/json' --data-binary "$LOGIN_PAYLOAD" "$BACKEND_URL/api/auth/login")"
TOKEN="$(printf '%s' "$LOGIN" | json_value 'd.get("access_token","")')"
[ -n "$TOKEN" ] || fail "platform admin login did not return a token"
if ! printf '%s' "$LOGIN" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "aitana-admin" in d["user"]["groupTags"]'; then
  fail "acceptance identity is not a platform admin"
fi
ok "Platform admin local-jwt login"

# Create a real private Skill owned by the authenticated admin. SkillConfig's
# canonical name is lowercase kebab-case; displayName remains human readable.
SKILL_NAME="mcp-live-${RUN_ID}"
SKILL_PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({"name":sys.argv[1],"description":"MCP live acceptance skill","instructions":"Use the bound map MCP server when asked.","displayName":"MCP Live Acceptance","accessControl":{"type":"private"},"skillMetadata":{}}))' "$SKILL_NAME")"
SKILL="$(curl -fsS -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary "$SKILL_PAYLOAD" "$BACKEND_URL/api/skills")"
SKILL_ID="$(printf '%s' "$SKILL" | json_value 'd.get("skillId","")')"
[ -n "$SKILL_ID" ] || fail "skill create did not return skillId"
ok "Acceptance Skill created through /api/skills"

SERVER_BODY_ENABLED="$(python3 -c 'import json,sys; print(json.dumps({"url":sys.argv[1],"transport":"streamable-http","scope":"platform","enabled":True,"description":"real self-host MCP acceptance"}))' "$UPSTREAM_URL")"
SERVER="$(curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary "$SERVER_BODY_ENABLED" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID")"
SERVER_CREATED=1
if ! printf '%s' "$SERVER" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["server_id"] and d["scope"]=="platform" and d["enabled"] is True'; then
  fail "MCP Admin create response is invalid"
fi
ok "MCP Server registered through Admin API"

# Health must be a genuine initialize handshake.
HEALTH="$(curl -fsS -X POST -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID/health")"
if ! printf '%s' "$HEALTH" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] is True and d.get("server")'; then
  echo "$HEALTH" >&2
  fail "MCP initialize health did not succeed"
fi
ok "Admin Health completed a real MCP initialize"

DISCOVERY="$(curl -fsS -X POST -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID/discover")"
printf '%s' "$DISCOVERY" > "$TMP_DIR/discovery.json"
if ! python3 - "$TMP_DIR/discovery.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p['ok'] is True, p
names=[str(t.get('name','')) for t in p.get('tools',[])]
assert names and any('map' in n.lower() for n in names), names
apps=p.get('mcp_apps') or {}
assert apps.get('supported') is True, apps
uris=[str(x) for x in apps.get('resourceUris',[])]
assert any(uri.startswith('ui://') for uri in uris), uris
PY
then
  cat "$TMP_DIR/discovery.json" >&2
  fail "MCP Discovery did not expose tool + MCP Apps resource"
fi
UI_URI="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(x for x in d["mcp_apps"]["resourceUris"] if x.startswith("ui://")))' "$TMP_DIR/discovery.json")"
ok "Admin Discovery returned tools and MCP Apps ui:// resource"

# Before a Skill binding exists, the authenticated browser-facing proxy must
# reject the server even though the admin can diagnose it.
INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"mcp-live-acceptance","version":"1"}}}'
PRE_BIND_CODE="$(curl -sS -o "$TMP_DIR/pre-bind.json" -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  --data-binary "$INIT_BODY" \
  "$BACKEND_URL/mcp/$SERVER_ID")"
[ "$PRE_BIND_CODE" = "403" ] || { cat "$TMP_DIR/pre-bind.json" >&2; fail "MCP proxy should be 403 before Skill binding, got $PRE_BIND_CODE"; }
ok "MCP proxy denies unbound server"

BIND_PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({"skillMetadata":{"toolConfigs":{"mcp":{"servers":[sys.argv[1]]}}}}))' "$SERVER_ID")"
BOUND="$(curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary "$BIND_PAYLOAD" "$BACKEND_URL/api/skills/$SKILL_ID")"
if ! printf '%s' "$BOUND" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["skillMetadata"]["toolConfigs"]["mcp"]["servers"]; assert sys.argv[1] in s' "$SERVER_ID"; then
  echo "$BOUND" >&2
  fail "Skill binding was not persisted"
fi
ok "MCP Server bound through normal Skill API"

# Run the real MCP SDK against the platform proxy from inside the backend
# container. This exercises Bearer auth, Skill allowlist, streamable HTTP,
# initialize, tools/list, resources/list and resources/read end-to-end.
PROXY_RESULT="$(docker compose exec -T backend uv run python scripts/verify_mcp_proxy_live.py \
  --proxy-url "http://127.0.0.1:1956/mcp/$SERVER_ID" \
  --token "$TOKEN" \
  --resource-uri "$UI_URI" | tail -n 1)"
printf '%s' "$PROXY_RESULT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] is True and d["htmlBytes"] > 0 and d["uiResource"].startswith("ui://")' || {
  echo "$PROXY_RESULT" >&2
  fail "real MCP proxy protocol verification failed"
}
ok "Authenticated MCP proxy transported initialize/tools/resources/read and HTML app resource"

# Disabled servers remain diagnosable by Admin but disappear from runtime/proxy.
SERVER_BODY_DISABLED="$(python3 -c 'import json,sys; print(json.dumps({"url":sys.argv[1],"transport":"streamable-http","scope":"platform","enabled":False,"description":"real self-host MCP acceptance"}))' "$UPSTREAM_URL")"
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary "$SERVER_BODY_DISABLED" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID" >/dev/null
DISABLED_HEALTH="$(curl -fsS -X POST -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID/health")"
printf '%s' "$DISABLED_HEALTH" | python3 -c 'import json,sys; assert json.load(sys.stdin)["ok"] is True' || fail "disabled MCP server should remain Admin-diagnosable"
DISABLED_CODE="$(curl -sS -o "$TMP_DIR/disabled.json" -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  --data-binary "$INIT_BODY" \
  "$BACKEND_URL/mcp/$SERVER_ID")"
[ "$DISABLED_CODE" = "404" ] || { cat "$TMP_DIR/disabled.json" >&2; fail "disabled MCP proxy should fail closed with 404, got $DISABLED_CODE"; }
ok "Disabled MCP stays diagnosable but runtime proxy fails closed"

printf '\nReal non-LLM MCP acceptance passed.\n'
printf 'Covered: Admin registration, real initialize Health, Discovery, Skill binding, proxy allowlist, tools/list, resources/read, MCP Apps HTML transport, disabled fail-closed.\n'
printf 'Still requires real model/browser acceptance: Agent-selected MCP Tool Call and iframe rendering.\n'

#!/usr/bin/env bash
# Administrator-managed shared MCP: registration, protocol, binding and revocation.
set -euo pipefail
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:1956}"
ADMIN_EMAIL="${SELFHOST_ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${SELFHOST_ADMIN_PASSWORD:?SELFHOST_ADMIN_PASSWORD is required}"
RUN_ID="${MCP_E2E_RUN_ID:-$(date +%s)-$RANDOM}"
RUN_ID="$(printf '%s' "$RUN_ID" | tr '[:upper:]_' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-24)"
SERVER_ID="mcp-live-${RUN_ID}"
TASK_DIR="$(mktemp -d)"
TOKEN=""
ROOT_SAVED=0
SERVER_CREATED=0
ROOT_PATH="$BACKEND_URL/api/admin/platform-config"
cleanup() {
  set +e
  if [ "$ROOT_SAVED" = "1" ]; then
    curl -fsS -o /dev/null -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary @"$TASK_DIR/root-original.json" "$ROOT_PATH"
  fi
  if [ "$SERVER_CREATED" = "1" ]; then
    curl -fsS -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID"
  fi
  rm -rf "$TASK_DIR"
}
trap cleanup EXIT
python3 - "$ADMIN_EMAIL" "$ADMIN_PASSWORD" > "$TASK_DIR/login.json" <<'PY'
import json,sys
print(json.dumps({'email':sys.argv[1],'password':sys.argv[2]}))
PY
curl -fsS -H 'content-type: application/json' --data-binary @"$TASK_DIR/login.json" "$BACKEND_URL/api/auth/login" > "$TASK_DIR/session.json"
TOKEN="$(python3 - "$TASK_DIR/session.json" <<'PY'
import json,sys
session=json.load(open(sys.argv[1])); assert 'aitana-admin' in session['user']['groupTags']; print(session['access_token'])
PY
)"
curl -fsS -H "Authorization: Bearer $TOKEN" "$ROOT_PATH" > "$TASK_DIR/root.json"
python3 - "$TASK_DIR" "$SERVER_ID" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); root=json.loads((p/'root.json').read_text())['agent']
(p/'root-original.json').write_text(json.dumps({'agent':root}))
(p/'root-grant.json').write_text(json.dumps({'agent':{**root,'mcpServers':list(dict.fromkeys(root['mcpServers']+[sys.argv[2]]))}}))
PY
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  --data '{"url":"http://mcp-example-map:8080/mcp","transport":"streamable-http","enabled":true,"description":"shared MCP acceptance"}' \
  "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID" > "$TASK_DIR/server.json"
SERVER_CREATED=1
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID/health" > "$TASK_DIR/health.json"
python3 - "$TASK_DIR/health.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['ok'] is True
PY
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID/discover" > "$TASK_DIR/discovery.json"
UI_URI="$(python3 - "$TASK_DIR/discovery.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1])); assert result['ok'] and result['tools']; print(next(x for x in result['mcp_apps']['resourceUris'] if x.startswith('ui://')))
PY
)"
INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"shared-mcp-acceptance","version":"1"}}}'
proxy_status() {
  curl -sS -o "$TASK_DIR/proxy.json" -w '%{http_code}' -X POST -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' --data-binary "$INIT_BODY" "$BACKEND_URL/mcp/$SERVER_ID"
}
[ "$(proxy_status)" = "403" ]
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary @"$TASK_DIR/root-grant.json" "$ROOT_PATH" > /dev/null
ROOT_SAVED=1
docker compose exec -T backend uv run python scripts/verify_mcp_proxy_live.py --proxy-url "http://127.0.0.1:1956/mcp/$SERVER_ID" --token "$TOKEN" --resource-uri "$UI_URI" > "$TASK_DIR/result.log"
tail -n 1 "$TASK_DIR/result.log" | python3 -c 'import json,sys; result=json.load(sys.stdin); assert result["ok"] and result["htmlBytes"] > 0'
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary @"$TASK_DIR/root-original.json" "$ROOT_PATH" > /dev/null
[ "$(proxy_status)" = "403" ]
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data-binary @"$TASK_DIR/root-grant.json" "$ROOT_PATH" > /dev/null
curl -fsS -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data '{"url":"http://mcp-example-map:8080/mcp","enabled":false}' "$BACKEND_URL/api/admin/mcp-servers/$SERVER_ID" > /dev/null
[ "$(proxy_status)" = "404" ]
printf 'Shared MCP acceptance passed: health, discovery, Agent binding, proxy tools/resources/Apps, immediate revocation and disabled access.\n'

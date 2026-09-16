#!/usr/bin/env bash
# Provider-independent self-host HTTP smoke test.
#
# By default this preserves the historical source-development expectation that
# LOCAL_MODE is enabled. Production-style Docker self-host sets LOCAL_MODE=0;
# callers should set EXPECT_LOCAL_MODE=false for that path.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:1956}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:3456}"
SANDBOX_URL="${SANDBOX_URL:-http://127.0.0.1:3457}"
EXPECT_LOCAL_MODE="${EXPECT_LOCAL_MODE:-true}"

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required." >&2
  exit 1
fi

failures=0

ok() { printf '✓ %s\n' "$1"; }
warn() { printf '! %s\n' "$1"; }
fail() { printf '✗ %s\n' "$1" >&2; failures=$((failures + 1)); }

probe_status() {
  local name="$1" url="$2" expected="${3:-200}"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "$url" 2>/dev/null || true)"
  if [ "$code" = "$expected" ]; then
    ok "$name ($url)"
  else
    fail "$name returned HTTP ${code:-unreachable}; expected $expected ($url)"
  fi
}

printf '\nAI Protocol Platform — self-host smoke\n'
printf 'Backend: %s\nFrontend: %s\nSandbox: %s\nExpected LOCAL_MODE: %s\n\n' \
  "$BACKEND_URL" "$FRONTEND_URL" "$SANDBOX_URL" "$EXPECT_LOCAL_MODE"

probe_status "Backend health" "$BACKEND_URL/health"

local_status="$(curl -fsS --max-time 8 "$BACKEND_URL/api/local-mode-status" 2>/dev/null || true)"
if [ "$EXPECT_LOCAL_MODE" = "true" ]; then
  if printf '%s' "$local_status" | grep -Eq '"local_mode"[[:space:]]*:[[:space:]]*true'; then
    ok "LOCAL_MODE is enabled"
  else
    fail "LOCAL_MODE is not enabled or /api/local-mode-status is unavailable"
  fi
else
  if printf '%s' "$local_status" | grep -Eq '"local_mode"[[:space:]]*:[[:space:]]*false'; then
    ok "LOCAL_MODE is disabled for production-style self-host"
  else
    fail "LOCAL_MODE is unexpectedly enabled or /api/local-mode-status is unavailable"
  fi
fi

# OpenAPI verifies FastAPI finished route registration without requiring a real
# provider call.
openapi="$(curl -fsS --max-time 8 "$BACKEND_URL/openapi.json" 2>/dev/null || true)"
if [ -n "$openapi" ]; then
  ok "FastAPI OpenAPI document is available"
else
  fail "FastAPI OpenAPI document is unavailable"
fi

if printf '%s' "$openapi" | grep -q '/api/skill/'; then
  ok "Skill streaming API is registered"
else
  fail "Skill streaming API was not found in OpenAPI"
fi

if printf '%s' "$openapi" | grep -Eqi 'mcp'; then
  ok "MCP-related API surface is registered"
else
  warn "No MCP route string found in OpenAPI"
fi

probe_status "Frontend" "$FRONTEND_URL"

sandbox_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$SANDBOX_URL" 2>/dev/null || true)"
if [ "$sandbox_code" = "200" ] || [ "$sandbox_code" = "404" ]; then
  ok "MCP Apps sandbox is listening (HTTP $sandbox_code)"
else
  warn "MCP Apps sandbox is not reachable on $SANDBOX_URL"
fi

printf '\nProvider-dependent acceptance still required separately:\n'
printf '  [ ] Run a normal chat/Runtime Skill turn against a real Provider\n'
printf '  [ ] Confirm real Provider Tool Calling\n'
printf '  [ ] Confirm a real model chooses and executes a bound MCP Tool\n'
printf '  [ ] Verify final Tenant quota / Tool Permission / Model Policy on that live path\n\n'

if [ "$failures" -gt 0 ]; then
  echo "Smoke test failed with $failures blocking check(s)." >&2
  exit 1
fi

echo "Automated self-host HTTP smoke checks passed."

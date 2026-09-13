#!/usr/bin/env bash
# Phase 0 self-hosted smoke test.
#
# Preconditions:
#   1. Configure backend/.env (see .env.selfhost.example)
#   2. Start the platform with: make dev-local
#   3. Run this script from the repository root
#
# This test is intentionally provider-independent at the HTTP layer. It verifies
# the LOCAL_MODE runtime, API surface, frontend bridge and MCP Apps sandbox.
# LLM/A2UI round-trip checks remain explicit manual acceptance steps because they
# consume a real model and depend on the configured provider.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:1956}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:3456}"
SANDBOX_URL="${SANDBOX_URL:-http://127.0.0.1:3457}"

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

printf '\nAI Protocol Platform — Phase 0 self-host smoke\n'
printf 'Backend: %s\nFrontend: %s\nSandbox: %s\n\n' "$BACKEND_URL" "$FRONTEND_URL" "$SANDBOX_URL"

# Backend process and LOCAL_MODE state.
probe_status "Backend health" "$BACKEND_URL/health"

local_status="$(curl -fsS --max-time 8 "$BACKEND_URL/api/local-mode-status" 2>/dev/null || true)"
if printf '%s' "$local_status" | grep -Eq '"local_mode"[[:space:]]*:[[:space:]]*true'; then
  ok "LOCAL_MODE is enabled"
else
  fail "LOCAL_MODE is not enabled or /api/local-mode-status is unavailable"
fi

# OpenAPI is useful here because it verifies FastAPI finished route registration,
# including the custom protocol routes, without relying on implementation details.
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

# MCP routes have changed names across upstream releases; treat absence as a
# warning rather than producing a false-negative on an otherwise healthy fork.
if printf '%s' "$openapi" | grep -Eqi 'mcp'; then
  ok "MCP-related API surface is registered"
else
  warn "No MCP route string found in OpenAPI; verify MCP manually before closing Issue #1"
fi

# Frontend and sandbox.
probe_status "Frontend" "$FRONTEND_URL"

sandbox_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$SANDBOX_URL" 2>/dev/null || true)"
if [ "$sandbox_code" = "200" ] || [ "$sandbox_code" = "404" ]; then
  # 404 is acceptable: it proves the isolated sandbox server is listening even
  # when it has no index route and serves only generated app resources.
  ok "MCP Apps sandbox is listening (HTTP $sandbox_code)"
else
  warn "MCP Apps sandbox is not reachable on $SANDBOX_URL. Install its npm dependencies if MCP Apps are required."
fi

printf '\nManual protocol acceptance checklist (requires a real LLM call):\n'
printf '  [ ] Open %s and confirm the LOCAL_MODE banner\n' "$FRONTEND_URL"
printf '  [ ] Run a normal chat turn\n'
printf '  [ ] Select the seeded Workspace Demo skill\n'
printf '  [ ] Ask: "show me the dashboard" and confirm an A2UI surface renders\n'
printf '  [ ] Trigger an A2UI action and confirm the action reaches the Agent\n'
printf '  [ ] Run one MCP tool-backed turn\n'
printf '  [ ] Render one MCP App inside the sandboxed iframe\n\n'

if [ "$failures" -gt 0 ]; then
  echo "Smoke test failed with $failures blocking check(s)." >&2
  exit 1
fi

echo "Automated Phase 0 smoke checks passed. Complete the manual protocol checklist before closing Issue #1."

#!/bin/sh
set -eu

# NEXT_PUBLIC_* values are compiled into the Next.js bundle. Release images use
# deliberately unique placeholders for values that must remain configurable at
# container startup, then this entrypoint rewrites the generated bundle.
MCP_PLACEHOLDER='https://mcp-sandbox.runtime.invalid'
MCP_RUNTIME_VALUE="${MCP_SANDBOX_PUBLIC_URL:-}"
AUTH_PLACEHOLDER='__aip_auth_mode_runtime__'
AUTH_RUNTIME_VALUE="${AUTH_BACKEND:-local-jwt}"

replace_bundle_value() {
  placeholder="$1"
  runtime_value="$2"
  [ -n "$runtime_value" ] || return 0

  escaped_value=$(printf '%s' "$runtime_value" | sed 's/[&|]/\\&/g')
  for root in /app/.next /app/public; do
    [ -d "$root" ] || continue
    grep -RIl -- "$placeholder" "$root" 2>/dev/null | while IFS= read -r file; do
      sed -i "s|$placeholder|$escaped_value|g" "$file"
    done
  done
}

replace_bundle_value "$MCP_PLACEHOLDER" "$MCP_RUNTIME_VALUE"
replace_bundle_value "$AUTH_PLACEHOLDER" "$AUTH_RUNTIME_VALUE"

exec "$@"

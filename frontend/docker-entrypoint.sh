#!/bin/sh
set -eu

# NEXT_PUBLIC_* values are compiled into the Next.js bundle. Release images use
# a deliberately unique, syntactically valid URL placeholder for the MCP Apps
# sandbox origin, then this entrypoint replaces it from runtime env so one GHCR
# image can be deployed on different hosts without rebuilding the frontend.
PLACEHOLDER='https://mcp-sandbox.runtime.invalid'
RUNTIME_VALUE="${MCP_SANDBOX_PUBLIC_URL:-}"

if [ -n "$RUNTIME_VALUE" ]; then
  ESCAPED_VALUE=$(printf '%s' "$RUNTIME_VALUE" | sed 's/[&|]/\\&/g')
  for root in /app/.next /app/public; do
    [ -d "$root" ] || continue
    grep -RIl -- "$PLACEHOLDER" "$root" 2>/dev/null | while IFS= read -r file; do
      sed -i "s|$PLACEHOLDER|$ESCAPED_VALUE|g" "$file"
    done
  done
fi

exec "$@"

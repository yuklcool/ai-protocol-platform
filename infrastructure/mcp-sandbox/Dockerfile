# AI Protocol Platform MCP App sandbox proxy — production image.
#
# The browser bridge and TypeScript server are built in a disposable stage.
# The final runtime contains only Node, production dependencies, the compiled
# server, static sandbox assets, and curated artefacts. Build/test tooling and
# npm itself are deliberately excluded from the production image so release
# vulnerability scanning reflects the actual runtime attack surface.

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY src ./src
COPY sandbox.html serve.ts ./

# Static artefacts can include fetched/pinned WASM assets in CI.
COPY artefacts ./artefacts

# Build the browser bridge and compile the tiny TypeScript HTTP server to ESM.
# Keep npm packages external so the runtime can use the production-only
# node_modules tree instead of bundling development dependencies.
RUN npm run build \
    && npx esbuild serve.ts \
      --bundle \
      --platform=node \
      --format=esm \
      --target=node22 \
      --packages=external \
      --outfile=serve.mjs


FROM node:22-alpine AS prod-deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --no-audit --no-fund


FROM node:22-alpine AS runtime

WORKDIR /app

# The official Node image includes npm and its large dependency tree. The
# sandbox never installs packages at runtime, so keeping npm only increases the
# production attack surface and causes unrelated npm-tooling CVEs to ship.
RUN rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx

COPY --from=prod-deps /app/node_modules ./node_modules
COPY --from=build /app/serve.mjs ./serve.mjs
COPY --from=build /app/public ./public
COPY --from=build /app/artefacts ./artefacts

# Cloud Run sets PORT=8080; local Compose may override SANDBOX_PORT instead.
ENV PORT=8080
EXPOSE 8080

CMD ["node", "serve.mjs"]

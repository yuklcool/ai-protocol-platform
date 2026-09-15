# Self-host convenience targets layered on top of the upstream-compatible Makefile.
# GNU Make prefers GNUmakefile when present; include the existing Makefile so all
# historical targets remain available unchanged.
include Makefile

.PHONY: docker-up docker-down docker-restart docker-ps docker-logs selfhost-smoke

# Build and start the production-style self-host stack declared in
# docker-compose.yml. Configure .env first (see .env.selfhost.example).
docker-up:
	@docker compose up -d --build
	@docker compose ps

# Stop containers but keep PostgreSQL/ObjectStorage named volumes intact.
docker-down:
	@docker compose down

# Restart the self-host stack without deleting persistent volumes.
docker-restart:
	@docker compose restart
	@docker compose ps

# Show the current self-host container/health state.
docker-ps:
	@docker compose ps

# Follow logs for the complete self-host stack.
docker-logs:
	@docker compose logs -f --tail=200

# Run the checked-in self-host smoke probes against the default local ports.
# Override BACKEND_URL / FRONTEND_URL / SANDBOX_URL when testing through a
# reverse proxy or non-default port mapping.
selfhost-smoke:
	@BACKEND_URL=$${BACKEND_URL:-http://127.0.0.1:1956} \
	 FRONTEND_URL=$${FRONTEND_URL:-http://127.0.0.1:3456} \
	 SANDBOX_URL=$${SANDBOX_URL:-http://127.0.0.1:3457} \
	 bash scripts/smoke-selfhost.sh

"""Seed repository-backed LOCAL_MODE data needed by self-hosted persistence.

The historical LOCAL_MODE fixture writes through the Firestore-compatible raw
client because many legacy domains still depend on that SDK surface. Once a
domain is migrated to ``db.persistence`` (Skills are the first one), a
PostgreSQL deployment must seed that domain in PostgreSQL as well.

This script is intentionally narrow and idempotent. It runs before uvicorn in
the Docker Compose backend and does nothing unless DATA_BACKEND=postgres.
"""

from __future__ import annotations

import logging
import time

from config.local_mode import is_local_mode
from db.local_fixture import _demo_skills
from db.persistence import data_backend, get_repository

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("seed_selfhost_persistence")


def main() -> None:
    if not is_local_mode():
        log.info("LOCAL_MODE is off; self-host fixture seed skipped")
        return
    if data_backend() != "postgres":
        log.info("DATA_BACKEND=%s; PostgreSQL fixture seed skipped", data_backend())
        return

    repo = get_repository()
    existing = repo.query_documents("skills", limit=1)
    if existing:
        log.info("PostgreSQL skills collection already seeded; no changes")
        return

    now = time.time()
    skills = _demo_skills(now)
    for skill in skills:
        repo.set_document("skills", skill["skillId"], skill)

    log.info("Seeded %d LOCAL_MODE demo skills into PostgreSQL", len(skills))


if __name__ == "__main__":
    main()

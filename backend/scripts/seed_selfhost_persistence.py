"""Seed repository-backed LOCAL_MODE data needed by self-hosted persistence.

The historical LOCAL_MODE fixture writes through the Firestore-compatible raw
client because some legacy domains still depend on that SDK surface. Domains
migrated to ``db.persistence`` must therefore be seeded in the selected
repository as well. This script runs before uvicorn in Docker Compose and is
idempotent.
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

    # SkillConfig now reads through db.persistence. Seed the same bundled demo
    # skills that the legacy LOCAL_MODE Firestore-compatible fixture exposes.
    if not repo.query_documents("skills", limit=1):
        now = time.time()
        skills = _demo_skills(now)
        for skill in skills:
            repo.set_document("skills", skill["skillId"], skill)
        log.info("Seeded %d LOCAL_MODE demo skills into PostgreSQL", len(skills))
    else:
        log.info("PostgreSQL skills collection already seeded; no changes")

    # auth.permissions is repository-backed as well. LOCAL_MODE is a
    # single-user sandbox, so mirror the existing in-memory wildcard grant.
    if repo.get_document("tool_permissions", "*") is None:
        repo.set_document(
            "tool_permissions",
            "*",
            {
                "type": "wildcard",
                "tools": ["*"],
                "denied": [],
                "note": "LOCAL_MODE wildcard — single-user sandbox; allow everything.",
            },
        )
        log.info("Seeded LOCAL_MODE wildcard tool permission into PostgreSQL")


if __name__ == "__main__":
    main()

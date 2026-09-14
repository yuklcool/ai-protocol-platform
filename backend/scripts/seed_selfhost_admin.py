"""Bootstrap the first built-in self-host administrator.

The script is intentionally idempotent and never rewrites an existing
credential on container restart. A first local-jwt deployment must provide
SELFHOST_ADMIN_EMAIL/PASSWORD; after an account exists those bootstrap secrets
may be removed from the environment.
"""

from __future__ import annotations

import os

from auth.admin_roles import PLATFORM_ADMIN_TAG
from auth.identity import auth_backend
from auth.local_jwt import (
    USER_COLLECTION,
    create_local_user,
    get_local_user_by_email,
    validate_local_jwt_config,
)
from db import persistence


def _has_any_local_user() -> bool:
    return bool(persistence.query_documents(USER_COLLECTION, limit=1))


def main() -> int:
    if auth_backend() != "local-jwt":
        print("self-host admin bootstrap: skipped (AUTH_BACKEND is not local-jwt)")
        return 0

    # Validate signing/expiry settings before uvicorn starts. A deployment that
    # cannot mint or verify tokens must fail at boot, not on the first login.
    validate_local_jwt_config()

    email = os.environ.get("SELFHOST_ADMIN_EMAIL", "").strip()
    password = os.environ.get("SELFHOST_ADMIN_PASSWORD", "")
    if not email and not password:
        if _has_any_local_user():
            print("self-host admin bootstrap: existing local account found; bootstrap credentials not required")
            return 0
        raise SystemExit(
            "AUTH_BACKEND=local-jwt requires SELFHOST_ADMIN_EMAIL and "
            "SELFHOST_ADMIN_PASSWORD on first startup"
        )
    if not email or not password:
        raise SystemExit(
            "SELFHOST_ADMIN_EMAIL and SELFHOST_ADMIN_PASSWORD must be configured together"
        )

    if get_local_user_by_email(email) is not None:
        print("self-host admin bootstrap: account already exists; leaving credentials unchanged")
        return 0

    user = create_local_user(
        email=email,
        password=password,
        group_tags={PLATFORM_ADMIN_TAG},
    )
    print(f"self-host admin bootstrap: created uid={user.uid} domain={user.domain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bootstrap the first built-in self-host administrator.

The script is intentionally idempotent and never rewrites an existing
credential on container restart. Set SELFHOST_ADMIN_EMAIL/PASSWORD only for the
initial account creation; later user-management work should mutate accounts
through authenticated admin APIs rather than environment variables.
"""

from __future__ import annotations

import os

from auth.admin_roles import PLATFORM_ADMIN_TAG
from auth.identity import auth_backend
from auth.local_jwt import create_local_user, get_local_user_by_email


def main() -> int:
    if auth_backend() != "local-jwt":
        print("self-host admin bootstrap: skipped (AUTH_BACKEND is not local-jwt)")
        return 0

    email = os.environ.get("SELFHOST_ADMIN_EMAIL", "").strip()
    password = os.environ.get("SELFHOST_ADMIN_PASSWORD", "")
    if not email and not password:
        print("self-host admin bootstrap: no credentials configured; no account created")
        return 0
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

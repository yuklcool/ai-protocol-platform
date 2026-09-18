"""Link an external OIDC subject to an existing local platform user."""

from __future__ import annotations

import argparse

from auth.oidc import link_oidc_subject


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link an OIDC issuer/subject to an existing auth_users account."
    )
    parser.add_argument("--issuer", required=True, help="Exact OIDC issuer URL")
    parser.add_argument("--subject", required=True, help="External OIDC sub claim")
    parser.add_argument("--email", required=True, help="Existing local platform user email")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing mapping for the same issuer/subject",
    )
    args = parser.parse_args()
    link_oidc_subject(
        issuer=args.issuer,
        subject=args.subject,
        email=args.email,
        overwrite=args.overwrite,
    )
    print(f"linked OIDC subject {args.subject!r} to local user {args.email.casefold()!r}")


if __name__ == "__main__":
    main()

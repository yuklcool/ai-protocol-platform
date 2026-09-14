"""Channel-to-platform identity resolution.

Maps channel-native user IDs (Telegram user ID, email address, Discord
snowflake) to internal user IDs in ``channel_identities``. Persistence is routed
through ``db.persistence`` so channel identity mapping also works in self-hosted
PostgreSQL deployments.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from db import persistence as fs

logger = logging.getLogger(__name__)

COLLECTION = "channel_identities"


def _doc_id(channel: str, channel_user_id: str) -> str:
    """Build the deterministic identity document ID."""
    if "/" in channel_user_id:
        raise ValueError(f"channel_user_id contains '/': {channel_user_id!r}")
    return f"{channel}_{channel_user_id}"


def _now() -> str:
    """Return a JSON-portable UTC timestamp shared by all repositories."""
    return datetime.now(UTC).isoformat()


class IdentityResolver:
    """Stateless resolver. All entry points are classmethods."""

    @classmethod
    async def resolve(cls, channel: str, channel_user_id: str) -> str | None:
        """Look up the internal UID for a channel-native identifier."""
        doc_id = _doc_id(channel, channel_user_id)
        data = fs.get_document(COLLECTION, doc_id)
        if not data:
            return None

        uid = data.get("firebase_uid")
        if not uid:
            logger.warning("channel_identities/%s exists but has no firebase_uid", doc_id)
            return None

        try:
            fs.update_document(COLLECTION, doc_id, {"last_seen_at": _now()})
        except Exception:
            logger.debug("Failed to touch last_seen_at for %s", doc_id, exc_info=True)

        return str(uid)

    @classmethod
    async def auto_create(
        cls,
        channel: str,
        channel_user_id: str,
        *,
        email: str | None = None,
    ) -> str:
        """Create a deterministic channel identity mapping for an unknown user."""
        doc_id = _doc_id(channel, channel_user_id)
        firebase_uid = f"channel-{doc_id}"
        domain = email.split("@", 1)[1] if email and "@" in email else ""

        now = _now()
        record = {
            "channel": channel,
            "channel_user_id": channel_user_id,
            "firebase_uid": firebase_uid,
            "email": email or "",
            "domain": domain,
            "group_tags": [],
            "created_at": now,
            "last_seen_at": now,
        }

        fs.set_document(COLLECTION, doc_id, record)
        logger.info("auto-created channel_identity %s -> %s", doc_id, firebase_uid)
        return firebase_uid


__all__ = ["COLLECTION", "IdentityResolver"]

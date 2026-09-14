"""Anonymous group-ID authentication.

Anonymous groups are short-code sessions with no persistent end-user account or
PII.  The group definition is durable; per-process dictionaries are caches and
rate/session counters only.

Persistence deliberately goes through :mod:`db.persistence` so the same code
works with Memory, Firestore, and PostgreSQL.  A group must be durably written
before its code is returned.  Cache misses rehydrate from the configured
Repository, which also makes joins survive backend/container reconstruction.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass, field

import jwt

from auth.firebase_auth import User
from auth.group_rate_limit import TokenBucketRateLimiter
from db.persistence import get_document, set_document, update_document

logger = logging.getLogger(__name__)

GROUP_AUTH_SIGNING_SECRET_ENV = "GROUP_AUTH_SIGNING_SECRET"
AUTH_MODE = "anonymous_group_id"
JWT_ALGORITHM = "HS256"
DEFAULT_TTL_DAYS = 30
DEFAULT_MAX_CONCURRENT_SESSIONS = 100
DEFAULT_TOKEN_LIFETIME_SECONDS = 8 * 3600
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN_BEFORE_HYPHEN = 4
_CODE_LEN_AFTER_HYPHEN = 4
_UID_SUFFIX_BYTES = 16
_GROUPS_COLLECTION = "anon_groups"


class GroupNotFound(Exception):
    """Unknown group id."""


class GroupRevoked(Exception):
    """Group was explicitly revoked by its creator."""


class GroupExpired(Exception):
    """Group TTL elapsed."""


class GroupSessionCapExceeded(Exception):
    """Per-group daily session cap reached."""


class InvalidGroupToken(Exception):
    """A group token failed validation."""


class GroupPersistenceError(Exception):
    """A group could not be durably stored."""


@dataclass(frozen=True)
class GroupRecord:
    group_id: str
    creator_uid: str
    title: str
    skill_ids: tuple[str, ...]
    created_at: float
    expires_at: float
    max_concurrent_sessions: int


@dataclass(frozen=True)
class JoinResult:
    token: str
    uid: str
    expires_at: float


@dataclass
class AnonymousGroupAuth:
    """Process-local caches/counters for anonymous group auth."""

    groups: dict[str, GroupRecord] = field(default_factory=dict)
    revoked_group_ids: set[str] = field(default_factory=set)
    sessions_today: dict[tuple[str, str], int] = field(default_factory=dict)
    rate_limiter: TokenBucketRateLimiter = field(default_factory=TokenBucketRateLimiter)

    @classmethod
    def reset_for_tests(cls) -> None:
        _state.groups.clear()
        _state.revoked_group_ids.clear()
        _state.sessions_today.clear()
        _state.rate_limiter.reset_all()

    @classmethod
    def user_from_token(cls, token: str) -> User:
        claims = verify_group_token(token)
        return User(
            uid=claims["sub"],
            email="",
            domain="",
            group_tags=frozenset(),
            auth_mode=AUTH_MODE,
            group_id=claims["group_id"],
        )


# Keep this class-level injection point for the existing deterministic tests.
AnonymousGroupAuth.time_provider = staticmethod(time.time)
_state = AnonymousGroupAuth()


def _signing_secret() -> str:
    secret = os.environ.get(GROUP_AUTH_SIGNING_SECRET_ENV, "")
    if not secret:
        raise RuntimeError(
            f"{GROUP_AUTH_SIGNING_SECRET_ENV} env var is required for "
            "anonymous group-ID auth. Set it to a long random string "
            "(rotate to invalidate all live tokens)."
        )
    return secret


def _generate_code() -> str:
    return "-".join(
        [
            "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN_BEFORE_HYPHEN)),
            "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN_AFTER_HYPHEN)),
        ]
    )


def _today_iso() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(AnonymousGroupAuth.time_provider()))


def _synthesize_uid(group_id: str) -> str:
    cleaned = group_id.replace("-", "")
    return f"anon-{cleaned}-{secrets.token_hex(_UID_SUFFIX_BYTES)}"


def _check_group_active(record: GroupRecord) -> None:
    if record.group_id in _state.revoked_group_ids:
        raise GroupRevoked(f"group {record.group_id} has been revoked")
    if AnonymousGroupAuth.time_provider() >= record.expires_at:
        raise GroupExpired(f"group {record.group_id} expired")


def _record_to_doc(record: GroupRecord) -> dict:
    return {
        "group_id": record.group_id,
        "creator_uid": record.creator_uid,
        "title": record.title,
        "skill_ids": list(record.skill_ids),
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "max_concurrent_sessions": record.max_concurrent_sessions,
    }


def _doc_to_record(doc: dict) -> GroupRecord:
    return GroupRecord(
        group_id=doc["group_id"],
        creator_uid=doc["creator_uid"],
        title=doc["title"],
        skill_ids=tuple(doc.get("skill_ids") or ()),
        created_at=doc["created_at"],
        expires_at=doc["expires_at"],
        max_concurrent_sessions=doc["max_concurrent_sessions"],
    )


def _persist_group(record: GroupRecord, *, required: bool) -> None:
    """Persist a group through the configured Repository.

    Creation is fail-loud: returning a code that cannot survive a restart is a
    broken promise.  Refresh/revoke paths remain best-effort where the caller's
    in-process state has already been updated.
    """
    try:
        set_document(
            _GROUPS_COLLECTION,
            record.group_id,
            _record_to_doc(record),
            merge=True,
        )
    except Exception as exc:
        logger.exception("group_auth: failed to persist group=%s", record.group_id)
        if required:
            raise GroupPersistenceError(
                f"could not persist group {record.group_id}: the code would stop working "
                "when this instance restarts. Refusing to return a code that will not last."
            ) from exc


def _load_group_doc(group_id: str) -> dict | None:
    try:
        return get_document(_GROUPS_COLLECTION, group_id)
    except Exception:
        logger.exception("group_auth: failed to load group=%s from repository", group_id)
        return None


def _load_group(group_id: str) -> GroupRecord | None:
    doc = _load_group_doc(group_id)
    if not doc:
        return None
    if doc.get("revoked"):
        _state.revoked_group_ids.add(group_id)
        return None
    try:
        return _doc_to_record(doc)
    except (KeyError, TypeError, ValueError):
        logger.exception("group_auth: invalid persisted group document group=%s", group_id)
        return None


def _mark_revoked(group_id: str) -> None:
    try:
        update_document(_GROUPS_COLLECTION, group_id, {"revoked": True})
    except Exception:
        logger.exception("group_auth: failed to persist revocation group=%s", group_id)


def _code_exists(code: str) -> bool:
    if code in _state.groups or code in _state.revoked_group_ids:
        return True
    try:
        return get_document(_GROUPS_COLLECTION, code) is not None
    except Exception:
        # Persistence is checked fail-loud immediately after code generation;
        # do not make a transient read failure prevent an otherwise valid create.
        return False


def create_group(
    *,
    title: str,
    skill_ids: list[str] | tuple[str, ...],
    creator_uid: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
    max_concurrent_sessions: int = DEFAULT_MAX_CONCURRENT_SESSIONS,
) -> GroupRecord:
    _signing_secret()

    now = AnonymousGroupAuth.time_provider()
    code = _generate_code()
    while _code_exists(code):
        code = _generate_code()

    record = GroupRecord(
        group_id=code,
        creator_uid=creator_uid,
        title=title,
        skill_ids=tuple(skill_ids),
        created_at=now,
        expires_at=now + ttl_days * 86400,
        max_concurrent_sessions=max_concurrent_sessions,
    )

    _persist_group(record, required=True)
    _state.groups[code] = record
    logger.info(
        "group_auth: created group=%s creator=%s ttl_days=%d skills=%d cap=%d",
        code,
        creator_uid,
        ttl_days,
        len(skill_ids),
        max_concurrent_sessions,
    )
    return record


def get_group(group_id: str) -> GroupRecord | None:
    """Return an active group, rehydrating from the Repository on cache miss."""
    if group_id in _state.revoked_group_ids:
        return None
    cached = _state.groups.get(group_id)
    if cached is not None:
        return cached

    loaded = _load_group(group_id)
    if loaded is not None:
        _state.groups[group_id] = loaded
    return loaded


def delete_group(group_id: str, requesting_uid: str) -> None:
    record = get_group(group_id)
    if record is None:
        raise GroupNotFound(f"group {group_id} not found")
    if record.creator_uid != requesting_uid:
        logger.warning(
            "group_auth: refused revoke uid=%s creator=%s group=%s",
            requesting_uid,
            record.creator_uid,
            group_id,
        )
        raise PermissionError(f"only the group's creator ({record.creator_uid}) may revoke it")

    _state.groups.pop(group_id, None)
    _state.revoked_group_ids.add(group_id)
    _mark_revoked(group_id)
    logger.info("group_auth: revoked group=%s by uid=%s", group_id, requesting_uid)


def join_group(group_id: str, *, client_ip: str) -> JoinResult:
    """Mint a token for a valid group code.

    Rate limiting happens before lookup so brute-force callers cannot use the
    endpoint as an existence oracle.  Crucially, lookup goes through
    :func:`get_group`, so a valid group survives process/container restart.
    """
    if not isinstance(group_id, str) or not group_id:
        raise ValueError("group_id must be a non-empty string")
    if not isinstance(client_ip, str) or not client_ip:
        raise ValueError("client_ip must be a non-empty string")

    _state.rate_limiter.check(client_ip)

    if group_id in _state.revoked_group_ids:
        raise GroupRevoked(f"group {group_id} has been revoked")

    record = get_group(group_id)
    if record is None:
        if group_id in _state.revoked_group_ids:
            raise GroupRevoked(f"group {group_id} has been revoked")
        raise GroupNotFound(f"group {group_id} not found")

    _check_group_active(record)

    cap_key = (group_id, _today_iso())
    current = _state.sessions_today.get(cap_key, 0)
    if current >= record.max_concurrent_sessions:
        raise GroupSessionCapExceeded(
            f"group {group_id} reached daily session cap ({record.max_concurrent_sessions})"
        )

    now = AnonymousGroupAuth.time_provider()
    uid = _synthesize_uid(group_id)
    exp = now + DEFAULT_TOKEN_LIFETIME_SECONDS
    claims = {
        "sub": uid,
        "group_id": group_id,
        "exp": exp,
        "iat": now,
        "auth_mode": AUTH_MODE,
    }
    token = jwt.encode(claims, _signing_secret(), algorithm=JWT_ALGORITHM)
    _state.sessions_today[cap_key] = current + 1
    logger.info(
        "group_auth: joined group=%s uid=%s session_n=%d",
        group_id,
        uid,
        current + 1,
    )
    return JoinResult(token=token, uid=uid, expires_at=exp)


def verify_group_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            _signing_secret(),
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidGroupToken("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidGroupToken(f"token invalid: {exc}") from exc

    required = {"sub", "group_id", "exp", "iat", "auth_mode"}
    if set(claims.keys()) != required:
        raise InvalidGroupToken(
            f"token claims must be {sorted(required)}; got {sorted(claims.keys())}"
        )
    if claims["auth_mode"] != AUTH_MODE:
        raise InvalidGroupToken(
            f"token auth_mode is {claims['auth_mode']!r}, expected {AUTH_MODE!r}"
        )

    group_id = claims["group_id"]
    if group_id in _state.revoked_group_ids:
        raise GroupRevoked(f"group {group_id} revoked")

    # On a reconstructed process, rehydrate the group so persisted revocation
    # and group expiry continue to be enforced rather than trusting JWT state
    # alone. Existing hot-cache verification remains an in-process lookup.
    record = _state.groups.get(group_id)
    if record is None:
        record = get_group(group_id)
        if group_id in _state.revoked_group_ids:
            raise GroupRevoked(f"group {group_id} revoked")
        if record is None:
            raise InvalidGroupToken(f"group {group_id} no longer exists")
    _check_group_active(record)

    return claims


__all__ = [
    "AUTH_MODE",
    "GROUP_AUTH_SIGNING_SECRET_ENV",
    "AnonymousGroupAuth",
    "GroupExpired",
    "GroupNotFound",
    "GroupRecord",
    "GroupRevoked",
    "GroupSessionCapExceeded",
    "InvalidGroupToken",
    "JoinResult",
    "create_group",
    "delete_group",
    "get_group",
    "join_group",
    "verify_group_token",
]

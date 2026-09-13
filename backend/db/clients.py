"""Client domain configuration and bucket resolution.

Client/tenant configuration is stored through the backend-neutral persistence
facade. This keeps the existing two-tier cache semantics while allowing the
same domain data to live in memory, Firestore, or PostgreSQL.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from pydantic import BaseModel, ConfigDict

from db.persistence import delete_document, get_document, set_document

log = logging.getLogger(__name__)

_COLLECTION = "clients"
_FAIL_CLOSED_TRUTHY = {"1", "true", "yes", "on"}


class UnmappedTenantError(Exception):
    """Raised when a domain has no bucket mapping and fail-closed is enabled."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        super().__init__(
            f"No document bucket is mapped for domain {domain!r} and the "
            "deployment is configured to fail closed (TENANT_FALLBACK_FAIL_CLOSED)."
        )


def _fail_closed() -> bool:
    return os.environ.get("TENANT_FALLBACK_FAIL_CLOSED", "").strip().lower() in _FAIL_CLOSED_TRUTHY


class ClientConfig(BaseModel):
    domain: str
    documents_bucket: str | None = None
    display_name: str = ""
    enabled_skills: list[str] | None = None
    derived_group_tags: list[str] | None = None
    default_skill: str | None = None

    model_config = ConfigDict(populate_by_name=True)


def get_client_sync(domain: str) -> ClientConfig | None:
    """Return the uncached ClientConfig for a domain, or None if not found."""
    data = get_document(_COLLECTION, domain)
    if data is None:
        return None
    data = {k: v for k, v in data.items() if k != "domain"}
    return ClientConfig(domain=domain, **data)


# Durable two-tier client-config cache. The backing durable cache now follows
# DATA_BACKEND as well, so PostgreSQL self-hosts do not silently write cache
# entries to Firestore.
_CACHE_COLLECTION = "client_config_cache"
_CACHE_MODULE_TTL = 60.0
_CACHE_DURABLE_TTL = 300.0
_CACHE_LOCK = threading.Lock()
_MISS = object()
_CLIENT_CACHE: dict[str, tuple[float, ClientConfig | None]] = {}


def _module_cache_get(domain: str):
    with _CACHE_LOCK:
        entry = _CLIENT_CACHE.get(domain)
        if entry is None:
            return _MISS
        expires_at, value = entry
        if time.time() > expires_at:
            del _CLIENT_CACHE[domain]
            return _MISS
        return value


def _module_cache_set(domain: str, value: ClientConfig | None) -> None:
    with _CACHE_LOCK:
        _CLIENT_CACHE[domain] = (time.time() + _CACHE_MODULE_TTL, value)


def _durable_cache_get(domain: str):
    """Best-effort durable cache read."""
    try:
        doc = get_document(_CACHE_COLLECTION, domain)
        if not doc:
            return _MISS
        expires_at = doc.get("expires_at")
        if isinstance(expires_at, (int, float)) and time.time() > expires_at:
            return _MISS
        if doc.get("absent"):
            return None
        config_data = doc.get("config")
        if not isinstance(config_data, dict):
            return _MISS
        config_data = {k: v for k, v in config_data.items() if k != "domain"}
        return ClientConfig(domain=domain, **config_data)
    except Exception as exc:
        log.debug("client_config_cache: durable read failed for %s: %s", domain, exc)
        return _MISS


def _durable_cache_set(domain: str, value: ClientConfig | None) -> None:
    """Best-effort durable cache write."""
    try:
        now = time.time()
        record: dict = {"domain": domain, "cached_at": now, "expires_at": now + _CACHE_DURABLE_TTL}
        if value is None:
            record["absent"] = True
        else:
            record["config"] = value.model_dump()
        set_document(_CACHE_COLLECTION, domain, record)
    except Exception as exc:
        log.debug("client_config_cache: durable write failed for %s: %s", domain, exc)


def get_client_cached(domain: str) -> ClientConfig | None:
    """Two-tier cached read of ``get_client_sync``."""
    if not domain:
        return None
    hit = _module_cache_get(domain)
    if hit is not _MISS:
        return hit  # type: ignore[return-value]
    durable = _durable_cache_get(domain)
    if durable is not _MISS:
        _module_cache_set(domain, durable)  # type: ignore[arg-type]
        return durable  # type: ignore[return-value]
    config = get_client_sync(domain)
    _module_cache_set(domain, config)
    if config is None or isinstance(config, ClientConfig):
        _durable_cache_set(domain, config)
    return config


def invalidate_client_cache(domain: str) -> None:
    if not domain:
        return
    with _CACHE_LOCK:
        _CLIENT_CACHE.pop(domain, None)
    try:
        delete_document(_CACHE_COLLECTION, domain)
    except Exception as exc:
        log.debug("client_config_cache: durable invalidate failed for %s: %s", domain, exc)


def _reset_client_cache() -> None:
    with _CACHE_LOCK:
        _CLIENT_CACHE.clear()


def _user_domain(user) -> str:  # type: ignore[no-untyped-def]
    domain = getattr(user, "domain", None)
    if domain:
        return domain
    email = getattr(user, "email", "") or ""
    return email.split("@")[1] if "@" in email else ""


def resolve_documents_bucket(user) -> str:  # type: ignore[no-untyped-def]
    """Return the object-storage bucket configured for the user's domain."""
    domain = _user_domain(user)
    client = get_client_sync(domain) if domain else None
    if client and client.documents_bucket:
        return client.documents_bucket
    if _fail_closed():
        raise UnmappedTenantError(domain or "(no domain)")
    return os.environ.get("DOCUMENTS_BUCKET", "aitana-documents-bucket")


def documents_bucket_for_domain(domain: str) -> str | None:
    if not domain:
        return None
    client = get_client_sync(domain)
    return client.documents_bucket if client and client.documents_bucket else None


def resolve_enabled_skills(user) -> list[str] | None:  # type: ignore[no-untyped-def]
    domain = _user_domain(user)
    if not domain:
        return None
    client = get_client_cached(domain)
    if client is None:
        return None
    return client.enabled_skills


def resolve_default_skill(user) -> str | None:  # type: ignore[no-untyped-def]
    domain = _user_domain(user)
    if not domain:
        return None
    client = get_client_cached(domain)
    if client is None:
        return None
    if client.default_skill:
        return client.default_skill
    if client.enabled_skills:
        return client.enabled_skills[0]
    return None


def resolve_derived_group_tags(domain: str) -> frozenset[str]:
    if not domain:
        return frozenset()
    client = get_client_cached(domain)
    if client is None or not client.derived_group_tags:
        return frozenset()
    return frozenset(client.derived_group_tags)


def resolve_channel_bucket() -> str:
    return os.environ.get("CHANNEL_DOCUMENTS_BUCKET") or os.environ.get(
        "DOCUMENTS_BUCKET", "aitana-documents-bucket"
    )

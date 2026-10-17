"""Backend-wide test fixtures.

Two concerns are handled here so individual tests don't have to:

  1. **GCP credentials.** `google.auth.default()` raises
     ``DefaultCredentialsError`` on a CI runner with no ADC, which makes
     the bare construction of any google-cloud-* client fail (e.g.
     ``firestore.Client()`` in ``db.firestore.get_client``,
     ``storage.Client()`` deep inside ``GcsArtifactService.__init__``).
     We replace ``google.auth.default`` with a stub that returns
     synthetic credentials + a fake project so client construction
     succeeds without hitting the auth subsystem. This is enough for
     tests that just need the *type* of a constructed client (e.g.
     ``test_with_bucket_env_returns_gcs``).

  2. **Firestore network calls.** ``db.firestore.get_client()`` is the
     single chokepoint for every read/write the v6 backend performs.
     Tests that mock specific helpers (``set_document``,
     ``query_documents``) but miss a code path that takes a Firestore
     round-trip the test didn't anticipate would otherwise hang or fail
     with auth errors. The autouse fixture below replaces the singleton
     with a ``MagicMock`` whose chained calls return sensibly-empty
     results — empty stream, no document found. Tests that genuinely
     want to assert on Firestore arguments still patch the helper they
     care about; this fixture just prevents accidental real calls.

Pre-2026-04-28 the test suite passed locally because every developer
had ADC configured; CI has been red since at least 2026-04-23 because
of the same. This file closes the gap so ``make test-fast`` is the
authoritative gate everywhere.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from types import SimpleNamespace
from unittest import mock

import pytest

_network_patch = None
_collection_credentials_patch = None


@pytest.fixture(autouse=True)
def _isolate_repository_and_memory_cache():
    from adk.session import _reset_memory_service_for_tests
    from db.persistence import reset_repository_for_testing
    from observability.tenant_context import _tenant_context

    if os.environ.get("RUN_LIVE_GCP") == "1":
        yield
        return
    reset_repository_for_testing()
    _reset_memory_service_for_tests()
    _tenant_context.set(None)
    yield
    reset_repository_for_testing()
    _reset_memory_service_for_tests()
    _tenant_context.set(None)


def pytest_sessionstart(session):
    """Optional hard network boundary for local, non-billable regression runs.

    Installed before test collection, so even an SDK constructor at module
    scope cannot contact a metadata service or a cloud identity endpoint.
    Compose/real-provider integration gates run separately without this flag.
    """
    del session
    # Fixtures run after collection. Some legacy modules construct SDK clients
    # at import time, so prevent ADC/metadata discovery before importing them.
    if os.environ.get("RUN_LIVE_GCP") != "1":
        import google.auth
        from google.auth.credentials import AnonymousCredentials

        global _collection_credentials_patch
        _collection_credentials_patch = pytest.MonkeyPatch()
        _collection_credentials_patch.setattr(
            google.auth, "default", lambda *args, **kwargs: (AnonymousCredentials(), "test-project")
        )
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
    if os.environ.get("AIP_TEST_ISOLATED_NETWORK") != "1":
        return
    global _network_patch
    _network_patch = pytest.MonkeyPatch()
    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def local(host):
        if host is None or host in ("localhost", b"localhost"):
            return True
        try:
            address = ipaddress.ip_address(host.decode() if isinstance(host, bytes) else host)
            return address.is_loopback or address.is_unspecified
        except ValueError:
            return False

    def connect(sock, address):
        if isinstance(address, tuple) and not local(address[0]):
            raise PermissionError("External network is disabled for isolated tests")
        return original_connect(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if not local(host):
            raise PermissionError("External DNS is disabled for isolated tests")
        return original_getaddrinfo(host, *args, **kwargs)

    _network_patch.setattr(socket.socket, "connect", connect)
    _network_patch.setattr(socket, "getaddrinfo", getaddrinfo)


def pytest_unconfigure(config):
    del config
    if _network_patch is not None:
        _network_patch.undo()
    if _collection_credentials_patch is not None:
        _collection_credentials_patch.undo()


@pytest.fixture(autouse=True)
def _isolate_firebase_directory_and_root_policy():
    """Unit auth doubles must not fall through to Identity Toolkit lookups.

    Token verification doubles alone do not cover channel UID enrichment,
    which also reads the Firebase user directory. Live GCP remains explicit.
    Root policy and directory caches are reset to avoid cross-test grants.
    """
    from auth.firebase_auth import clear_user_cache
    from config.platform_config import invalidate_cache

    clear_user_cache()
    invalidate_cache(clear_last_known_good=True)
    if os.environ.get("RUN_LIVE_GCP") == "1":
        yield
    else:
        from firebase_admin import _http_client
        from firebase_admin import auth as fb_auth

        with (
            mock.patch.object(fb_auth, "get_users", return_value=SimpleNamespace(users=[])),
            mock.patch.object(fb_auth, "list_users", return_value=SimpleNamespace(iterate_all=lambda: iter(()))),
            mock.patch.object(fb_auth, "verify_id_token", side_effect=fb_auth.InvalidIdTokenError("isolated verifier")),
            mock.patch.object(
                _http_client.HttpClient, "request", side_effect=RuntimeError("Firebase HTTP is disabled in unit tests")
            ),
            mock.patch.object(fb_auth, "get_user", side_effect=fb_auth.UserNotFoundError("isolated test directory")),
            mock.patch.object(
                fb_auth, "get_user_by_email", side_effect=fb_auth.UserNotFoundError("isolated test directory")
            ),
        ):
            yield
    clear_user_cache()
    invalidate_cache(clear_last_known_good=True)


# MODEL-RELIABILITY M3: the test suite runs under the `unrestricted`
# residency policy by default, mirroring the Aitana dev deployment (the
# accepted dev/demo US-egress exception) — provider-routing tests assert
# claude/gpt behavior that eu-strict correctly forbids. models.yaml ships
# `default_policy: eu-strict` as the fail-safe for real deployments;
# residency-specific tests (test_resolve_model_chain.py) override this
# per-test via monkeypatch.
os.environ.setdefault("MODEL_RESIDENCY_POLICY", "unrestricted")


@pytest.fixture(autouse=True, scope="session")
def _stub_gcp_default_credentials():
    """Replace google.auth.default() session-wide.

    google-cloud-* libraries call this once during ``Client.__init__``
    to resolve a credentials + project pair. Returning a synthetic pair
    lets construction succeed; actual API calls would still fail (we
    rely on either the per-test mocks or ``_stub_firestore_client``
    below to keep them from happening).

    Set ``RUN_LIVE_GCP=1`` to disarm the stub so ``-m integration``
    tests can reach real GCP with real ADC. Without the escape hatch,
    integration tests could never run live: the autospec'd Credentials
    lacks ``.token`` (an instance attribute, invisible to autospec), so
    any code path that got as far as ``credentials.token`` crashed with
    a Mock AttributeError instead of making a request
    (MODEL-RELIABILITY M0).
    """
    if os.environ.get("RUN_LIVE_GCP") == "1":
        yield
        return

    import google.auth
    import google.auth.credentials

    fake_creds = mock.create_autospec(google.auth.credentials.Credentials, instance=True)
    # google-cloud-* clients compare credentials.universe_domain against
    # the configured one; a bare MagicMock returns another MagicMock and
    # fails equality. Set the default explicitly.
    fake_creds.universe_domain = "googleapis.com"
    fake_project = "test-project"
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", fake_project)

    with mock.patch.object(google.auth, "default", return_value=(fake_creds, fake_project)):
        yield


@pytest.fixture(autouse=True)
def _stub_firestore_client():
    """Replace db.firestore._client per test with a MagicMock.

    Default chained-call returns:
      * ``collection().document().get()`` → ``exists=False``, ``to_dict()=None``
      * ``collection().where().limit().stream()`` → empty iterator
      * ``collection().where().order_by().limit().stream()`` → empty iterator

    Per-test patches of ``db.firestore.get_document`` /
    ``db.firestore.set_document`` /
    ``db.firestore.query_documents`` continue to work — they replace
    the module-level helpers, not the singleton.
    """
    import db.firestore as fs

    saved = fs._client
    fake = mock.MagicMock(name="firestore_client_stub")

    # Default doc-get: not found.
    doc_snapshot = mock.MagicMock(exists=False)
    doc_snapshot.to_dict.return_value = None
    fake.collection.return_value.document.return_value.get.return_value = doc_snapshot

    # Default streams: empty iterators (rebuilt per call so each call
    # gets its own iterator and doesn't see "already consumed").
    def _empty_iter(*_args, **_kwargs):
        return iter([])

    where_mock = fake.collection.return_value.where.return_value
    where_mock.limit.return_value.stream.side_effect = _empty_iter
    where_mock.order_by.return_value.limit.return_value.stream.side_effect = _empty_iter
    where_mock.stream.side_effect = _empty_iter

    fs._client = fake
    yield fake
    fs._client = saved


@pytest.fixture(autouse=True)
def _reset_client_config_cache():
    """Clear the in-process client-config cache (db/clients.py, v6.9.0 M4)
    before and after each test so a cached ClientConfig never leaks across
    tests. The durable Firestore tier is already stubbed empty per test by
    ``_stub_firestore_client`` above."""
    import db.clients as _clients

    _clients._reset_client_cache()
    yield
    _clients._reset_client_cache()


@pytest.fixture(autouse=True)
def _reset_agent_and_mcp_caches():
    """Clear the built-agent cache and the MCP registry config cache (v6.14.0)
    before and after each test — both are module-level TTL caches that would
    otherwise leak a cached agent / mcp_servers doc across tests (e.g. a test
    that mocks ``get_document`` would see a prior test's cached config)."""
    from adk import a2ui_sources_render as _sources
    from adk import agent_cache as _agent_cache
    from tools.mcp import registry as _mcp_registry

    _agent_cache.clear()
    _mcp_registry.clear_registry_cache()
    _sources.clear_resolution_cache()
    yield
    _agent_cache.clear()
    _mcp_registry.clear_registry_cache()
    _sources.clear_resolution_cache()

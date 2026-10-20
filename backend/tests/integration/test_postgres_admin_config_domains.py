from __future__ import annotations

import os
import uuid

import pytest

from db.persistence import reset_repository_for_testing


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration test")
    return value


def test_admin_config_domains_round_trip_through_postgres(monkeypatch, tmp_path):
    database_url = _database_url()
    monkeypatch.setenv("DATA_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_repository_for_testing(None)

    from db.persistence import get_repository

    repository = get_repository()
    suffix = uuid.uuid4().hex[:10]

    import config.platform_config as platform_config
    from db.models import PLATFORM_CONFIG_DOC_ID

    platform_config.invalidate_cache()
    preamble = f"postgres-platform-{suffix}"
    updated = platform_config.update_platform_config(
        {"preamble": preamble, "enabled": True},
        updated_by=f"ci-{suffix}",
    )
    platform_config.invalidate_cache()
    assert platform_config.get_platform_config().preamble == preamble
    assert updated.updated_by == f"ci-{suffix}"

    user_id = f"user-{suffix}"
    from db.user_profiles import UserProfile, get_user_profile, save_user_profile

    save_user_profile(user_id, UserProfile(information="postgres profile"))
    assert get_user_profile(user_id).information == "postgres profile"

    from auth import User
    from observability.user_context import set_user_context
    from tools.mcp.registry import _cached_server_config, clear_registry_cache

    server_id = f"mcp-{suffix}"
    repository.set_document(
        "mcp_servers",
        server_id,
        {
            "url": "https://mcp.example.test/mcp",
            "enabled": True,
        },
    )
    clear_registry_cache()
    set_user_context(User(uid="viewer"))
    assert _cached_server_config(server_id)["url"] == "https://mcp.example.test/mcp"
    set_user_context(User(uid="another-viewer"))
    assert _cached_server_config(server_id)["url"] == "https://mcp.example.test/mcp"
    clear_registry_cache()
    set_user_context(User(uid=""))

    repository.delete_document("mcp_servers", server_id)
    repository.delete_document("user_profiles", user_id)
    repository.delete_document(platform_config.COLLECTION, PLATFORM_CONFIG_DOC_ID)
    platform_config.invalidate_cache()
    reset_repository_for_testing(None)

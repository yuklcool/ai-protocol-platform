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

    # Platform config: exercise the real domain helper rather than Repository directly.
    import config.platform_config as platform_config

    platform_config.invalidate_cache()
    preamble = f"postgres-platform-{suffix}"
    updated = platform_config.update_platform_config(
        {"preamble": preamble, "enabled": True},
        updated_by=f"ci-{suffix}",
    )
    platform_config.invalidate_cache()
    assert platform_config.get_platform_config().preamble == preamble
    assert updated.updated_by == f"ci-{suffix}"

    # Group-tag registry: create through canonical persistence and read through
    # the admin domain helper. Structural Firebase identity enumeration is not
    # part of this persistence test.
    from admin import group_tags_routes

    tag_id = f"CI-{suffix}"
    repository.set_document(
        group_tags_routes.COLLECTION,
        tag_id,
        {"label": "CI group", "description": "postgres", "grants": []},
    )
    assert tag_id in group_tags_routes.registry_ids()

    # Access dry-run uses the same tool_permissions data as enforcement.
    from admin.access_routes import _explain_tool
    from auth import permissions as perms

    email = f"alice-{suffix}@example.com"
    repository.set_document(perms.COLLECTION, email, {"type": "user", "tools": ["search"]})
    allowed, reason = _explain_tool(email, "example.com", "search")
    assert allowed is True
    assert "user-level" in reason

    # MCP consistency checker must inspect PostgreSQL, not Firestore.
    from admin.mcp_registry_check import verify_mcp_registry

    server_id = "ext-apps-map"
    repository.set_document("mcp_servers", server_id, {"url": "https://mcp.example.test/mcp"})
    skill_dir = tmp_path / f"skill-{suffix}"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: skill-{suffix}\n"
        "description: postgres registry probe\n"
        "metadata:\n"
        "  toolConfigs:\n"
        "    mcp:\n"
        "      servers:\n"
        f"        - {server_id}\n"
        "---\n\nProbe.\n"
    )
    result = verify_mcp_registry(tmp_path, deployed=False)
    assert result["ok"] is True
    assert result["mcp_missing"] == []

    # Keep the ephemeral shared CI database tidy where practical.
    repository.delete_document(group_tags_routes.COLLECTION, tag_id)
    repository.delete_document(perms.COLLECTION, email)
    repository.delete_document("mcp_servers", server_id)
    repository.delete_document(platform_config.COLLECTION, "global")
    platform_config.invalidate_cache()
    reset_repository_for_testing(None)

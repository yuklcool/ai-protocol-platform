"""Destructive upgrade reset is tested in a disposable PostgreSQL schema."""

import json
import os
import uuid
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_reset_discards_old_ownership_without_reassigning_data():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration test")
    import asyncpg

    conn = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    schema = "user_reset_" + uuid.uuid4().hex
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        migrations = Path(__file__).resolve().parents[2] / "db" / "migrations"
        await conn.execute((migrations / "001_postgres_documents.sql").read_text())
        rows = [
            ("tenants", "old", {}),
            ("tenant_domains", "example.com", {}),
            ("permission_groups", "old", {}),
            (
                "auth_users",
                "alice",
                {
                    "uid": "alice",
                    "passwordHash": "unchanged",
                    "tenantId": "old",
                    "permissionGroupIds": ["old"],
                    "groupTags": ["tenant-admin:old", "aitana-admin"],
                },
            ),
            (
                "platform_config",
                "default",
                {"agent": {"skills": ["shared"], "tenantOverrides": {"old": {"skills": ["private"]}}}},
            ),
            ("skills", "shared", {"tenantId": "", "ownerId": "aitana-platform"}),
            ("skills", "private", {"tenantId": "old", "ownerId": "alice"}),
            ("parsed_documents", "old-document", {"tenantId": "old", "userId": "alice"}),
            ("mcp_servers", "private", {"scope": "tenant", "tenantId": "old"}),
            ("mcp_servers", "shared", {"scope": "platform", "enabled": True}),
            ("user_profiles", "alice", {"information": "personal"}),
            ("adk_memory_events_oldhash", "memory", {"userId": "alice"}),
            ("user_memory_events_newhash", "memory", {"userId": "alice"}),
        ]
        for collection, doc_id, data in rows:
            await conn.execute(
                "INSERT INTO platform_documents(collection,doc_id,data) VALUES($1,$2,$3::jsonb)",
                collection,
                doc_id,
                json.dumps(data),
            )
        await conn.execute("CREATE TABLE sessions(app_name text)")
        await conn.execute("INSERT INTO sessions VALUES('tenant-old--root-agent'),('user-alice--root-agent')")
        await conn.execute((migrations / "002_user_owned_reset.sql").read_text())
        remaining = {
            (row["collection"], row["doc_id"]): json.loads(row["data"])
            for row in await conn.fetch("SELECT collection,doc_id,data FROM platform_documents")
        }
        assert ("skills", "private") not in remaining
        assert ("parsed_documents", "old-document") not in remaining
        assert ("mcp_servers", "private") not in remaining
        assert ("adk_memory_events_oldhash", "memory") not in remaining
        assert remaining[("auth_users", "alice")] == {
            "uid": "alice",
            "passwordHash": "unchanged",
            "groupTags": ["aitana-admin"],
        }
        assert remaining[("platform_config", "default")] == {"agent": {"skills": ["shared"]}}
        assert ("user_memory_events_newhash", "memory") in remaining
        assert remaining[("user_profiles", "alice")] == {"information": "personal"}
        assert [row["app_name"] for row in await conn.fetch("SELECT app_name FROM sessions")] == [
            "user-alice--root-agent"
        ]
        # Re-running is safe and does not synthesize replacement ownership.
        await conn.execute((migrations / "002_user_owned_reset.sql").read_text())
    finally:
        await conn.execute("SET search_path TO public")
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()

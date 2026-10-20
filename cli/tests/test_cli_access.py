"""Tests for `aitana access` subcommands — wired to the v6.9.0 admin API (9.3).

Effective-access dry-run for a user against /api/admin/access/check.
"""

from __future__ import annotations

import json

import httpx
import respx
from click.testing import CliRunner

from aiplatform.cli import main

BASE = "http://localhost:1956"
EMAIL = "alice@example.com"


@respx.mock
def test_access_check_email_only() -> None:
    route = respx.post(f"{BASE}/api/admin/access/check").mock(
        return_value=httpx.Response(
            200, json={"skills": [{"id": "personal-skill", "label": "Personal Skill"}], "mcpServers": []}
        )
    )
    runner = CliRunner()
    result = runner.invoke(main, ["--env", "local", "access", "check", "--email", EMAIL])
    assert result.exit_code == 0, result.output
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"email": EMAIL}
    assert "personal-skill" in result.output


def test_access_check_requires_email() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--env", "local", "access", "check"])
    assert result.exit_code != 0
    assert "--email" in result.output

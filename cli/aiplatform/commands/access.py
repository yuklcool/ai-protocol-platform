"""Preview the shared Agent and personal capabilities available to an account."""

from __future__ import annotations

import json as _json

import click

from aiplatform.http import AIPlatformClient


def _client(ctx: click.Context) -> AIPlatformClient:
    return AIPlatformClient(env=ctx.obj["env"])


@click.group()
def access() -> None:
    """Access-control dry-run helpers."""


@access.command("check")
@click.option("--email", required=True, help="User email to inspect.")
@click.pass_context
def check(ctx: click.Context, email: str) -> None:
    """Show an account's effective Skill and MCP bindings."""
    payload: dict = {"email": email}
    result = _client(ctx).post("/api/admin/access/check", json=payload)
    click.echo(_json.dumps(result, indent=2))

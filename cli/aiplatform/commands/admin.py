"""Inspect platform administration authority with /api/admin/whoami."""

from __future__ import annotations

import click

from aiplatform.http import AIPlatformClient


def _client(ctx: click.Context) -> AIPlatformClient:
    return AIPlatformClient(env=ctx.obj["env"])


@click.group()
def admin() -> None:
    """Admin-scope helpers."""


@admin.command("whoami")
@click.pass_context
def whoami(ctx: click.Context) -> None:
    """Show your resolved admin scope (platform / none)."""
    payload = _client(ctx).get("/api/admin/whoami")
    scope = str(payload.get("scope") or "none")
    email = str(payload.get("email") or "")

    if email:
        click.echo(f"Signed in as: {email}")

    if scope == "platform":
        click.echo("Admin scope:   platform (aitana-admin)")
    else:
        click.echo("Admin scope:   none — you are not an admin in this environment")
        click.echo("Ask a platform administrator to grant access in this environment, then sign out and back in.")

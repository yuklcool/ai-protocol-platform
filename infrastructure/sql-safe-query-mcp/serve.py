"""Expose the migrated Skill's original example retriever over MCP."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse


def create_server(skill_root: Path) -> FastMCP:
    for relative in (
        "scripts/retrieve_examples.py",
        "data/training_data.json",
        "data/text2sql_index.json",
        "data/sql_templates.json",
    ):
        if not (skill_root / relative).is_file():
            raise FileNotFoundError(f"Incomplete sql-safe-query Skill: {relative}")

    spec = importlib.util.spec_from_file_location(
        "sql_safe_query_retriever", skill_root / "scripts/retrieve_examples.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    server = FastMCP(
        "sql-safe-query-examples",
        host="0.0.0.0",
        port=8011,
        stateless_http=True,
        json_response=True,
        log_level="WARNING",
        transport_security=TransportSecuritySettings(
            allowed_hosts=["sql-safe-query-mcp:8011", "127.0.0.1:8011", "localhost:8011"],
        ),
    )

    @server.tool()
    def sql_retrieve_examples(
        question: Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")],
        top_k: Annotated[int, Field(ge=1, le=5)] = 5,
    ) -> dict[str, Any]:
        """Retrieve lighting SQL examples, templates and relevant schemas.

        Use only when no fully applicable verified OpenViking case exists.
        These are reference candidates, not freshly verified business results.
        This tool reads static Skill data; it never executes SQL or commands.
        """
        return module.retrieve(question.strip(), top_k=top_k, top_k_templates=3)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    return server


if __name__ == "__main__":
    create_server(Path(os.environ.get("SQL_SAFE_QUERY_DIR", "/skill"))).run(
        transport="streamable-http"
    )

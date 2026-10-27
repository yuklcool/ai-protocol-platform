"""Isolated CI read-only MCP fixture. No production network or database."""

import json
import re

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from lighting.results import LightingResult, normalize
from tests.fixtures.lighting_results import fixture

server = FastMCP("lighting-ci-fixture", host="0.0.0.0", port=8090, stateless_http=True, json_response=True)
calls = []


def result_for(request: dict) -> dict:
    """Build explicitly synthetic evidence for the requested CI interaction."""
    intent = request.get("intent")
    scene = {
        "inspect_lamp": "lamp_alarms",
        "compare_circuit": "lamp_alarms",
        "inspect_rtu": "rtu",
        "downstream": "lamp_alarms",
        "energy_view": "energy",
    }.get(intent, request.get("scene", "night"))
    result = fixture(scene, request.get("energy_view") or "night", status=request.get("fixture_status", "success"))
    if request.get("source_query_id"):
        for key in ("scope", "window", "timezone", "cutoff", "basis", "report_type", "rtu_energy_window"):
            result["query"][key] = request[key]
    return normalize(LightingResult.model_validate(result)).model_dump(mode="json")


@server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def sql_query_readonly(sql: str, max_rows: int = 1, request_id: str = None) -> dict:
    """CI SQL boundary; metadata chooses synthetic evidence, never a business DB."""
    match = re.search(r"/\* fixture:(.*?) \*/", sql)
    if not match or "lighting-query/v1" not in sql or max_rows != 1:
        raise ValueError("Invalid synthetic query")
    request = json.loads(match[1])
    calls.append(request)
    del calls[:-100]
    return {"ok": True, "rows": [{"payload": result_for(request)}], "meta": {"truncated": False}}


@server.custom_route("/evidence", methods=["GET"])
async def evidence(_request):
    return JSONResponse({"synthetic": True, "calls": calls})


if __name__ == "__main__":
    server.run(transport="streamable-http")

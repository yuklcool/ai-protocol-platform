"""Isolated CI read-only MCP fixture. No production network or database."""

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from lighting.results import LightingResult, normalize
from tests.fixtures.lighting_results import fixture

server = FastMCP("lighting-ci-fixture", host="0.0.0.0", port=8090, stateless_http=True, json_response=True)
calls = []


@server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def query_lighting(request: dict) -> dict:
    """Read synthetic lighting evidence. request carries scene, intent and time context."""
    calls.append(request)
    del calls[:-100]
    intent = request.get("intent")
    scene = {
        "inspect_lamp": "lamp_alarms",
        "compare_circuit": "lamp_alarms",
        "inspect_rtu": "rtu",
        "downstream": "lamp_alarms",
        "energy_view": "energy",
    }.get(intent, request.get("scene", "night"))
    result = fixture(scene, request.get("energy_view") or "night", status=request.get("fixture_status", "success"))
    # The controlled query service returns its computed facts to BOTH model
    # and renderer. The model must not calculate from raw rows itself.
    return normalize(LightingResult.model_validate(result)).model_dump(mode="json")


@server.custom_route("/evidence", methods=["GET"])
async def evidence(_request):
    return JSONResponse({"synthetic": True, "calls": calls})


if __name__ == "__main__":
    server.run(transport="streamable-http")

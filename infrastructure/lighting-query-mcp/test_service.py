"""Runs on GitHub against disposable PostgreSQL, never the business DB."""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys

import asyncpg
from mcp.types import CallToolResult, TextContent
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lighting.results import LightingResult
from presenter import present
from queries import build_query, literal, scope_query
from request import LightingRequest
from serve import LightingService, RequireToken, create_server, unwrap_sql

NOW = datetime.fromisoformat("2026-10-26T12:00:00+08:00")


def request(scene, **kwargs):
    params = {"scene": scene, **kwargs}
    if scene in {"night", "rtu", "lamp_alarms", "rtu_alarms"} or kwargs.get("energy_view") == "night":
        params["window"] = {"start": "2026-10-24T18:00:00+08:00", "end": "2026-10-25T07:00:00+08:00"}
    return LightingRequest.model_validate(params).resolve(NOW)


async def read(sql):
    connection = await asyncpg.connect(os.environ["LIGHTING_TEST_DATABASE_URL"])
    try:
        return json.loads(await connection.fetchval(sql))
    finally:
        await connection.close()


@pytest.fixture(scope="module", autouse=True)
def database():
    async def prepare():
        conn = await asyncpg.connect(os.environ["LIGHTING_TEST_DATABASE_URL"])
        try:
            await conn.execute(Path(__file__).with_name("test_schema.sql").read_text())
        finally:
            await conn.close()
    asyncio.run(prepare())


@pytest.mark.parametrize("scene,view", [("night", None), ("lamp_alarms", None), ("rtu", None), ("rtu_alarms", None), ("reconcile", None), ("energy", "night"), ("energy", "week"), ("energy", "volatility"), ("energy", "saving")])
def test_real_postgres_queries_validate_against_shipped_contract(scene, view):
    req = request(scene, energy_view=view)
    data = asyncio.run(read(build_query(req)))
    alarms = None
    if scene in {"night", "rtu"}:
        alarm_req = req.model_copy(update={"scene": "lamp_alarms" if scene == "night" else "rtu_alarms"})
        alarms = asyncio.run(read(build_query(alarm_req)))
    result = present(req, data, NOW, alarms)
    validated = LightingResult.model_validate(result)
    assert validated.rows
    assert validated.status == "partial"
    assert all(not row.relationship_verified for row in validated.rows)
    if scene == "night":
        assert len(validated.report) == 9
    if scene == "rtu":
        assert len(validated.report) == 7


def test_truncation_never_changes_population_and_reset_never_becomes_consumption():
    req = request("night", limit=1)
    data = asyncio.run(read(build_query(req)))
    assert data["row_count"] == 3
    assert len(data["rows"]) == 1
    assert data["totals"]["observed"] == 2
    assert data["totals"]["valid_energy"] == 1
    assert data["totals"]["actual_kwh"] == 1
    assert present(req, data, NOW)["complete"] is False


def test_calendar_pairing_does_not_use_previous_available_day_and_duplicate_reports_are_invalid():
    req = request("energy", energy_view="volatility")
    data = asyncio.run(read(build_query(req)))
    by_id = {row["id"]: row for row in present(req, data, NOW)["rows"]}
    assert by_id["r1_2026-10-25"]["values"]["increase_flag"] is True
    assert by_id["r2_2026-10-25"]["values"]["previous_kwh"] is None
    assert by_id["r2_2026-10-25"]["values"]["increase_flag"] is False
    assert by_id["r2_2026-10-24"]["values"]["actual_kwh"] is None


def test_reconciliation_preserves_zero_missing_filters_and_historical_uncertainty():
    req = request("reconcile")
    result = present(req, asyncio.run(read(build_query(req))), NOW)
    row = next(row for row in result["rows"] if row["rtu_id"] == "r1")
    assert row["values"]["lamp_kwh"] == 20
    assert row["values"]["rtu_kwh"] == 160
    assert row["values"]["ledger_difference_kwh"] == -140
    assert row["values"]["difference_kwh"] is None
    assert row["values"]["ratio"] is None
    assert row["values"]["status"] == "证据不足"


def test_saving_uses_weighted_totals_and_never_invents_target():
    req = request("energy", energy_view="saving")
    result = present(req, asyncio.run(read(build_query(req))), NOW)
    weighted = next(metric for metric in result["metrics"] if metric["label"] == "有效样本加权节能率")
    assert weighted["value"] == pytest.approx(0.3)
    assert all(row["values"]["target_status"] == "未取得目标或有效能耗" for row in result["rows"])


def test_scope_is_exact_and_quoted_values_cannot_change_sql():
    req = request("rtu", scope="控制箱一")
    assert asyncio.run(read(scope_query(req)))["row_count"] == 1
    assert asyncio.run(read(build_query(req)))["row_count"] == 1
    req.scope = "x' OR TRUE --"
    assert asyncio.run(read(build_query(req)))["row_count"] == 0
    with pytest.raises(ValueError):
        literal("x\\y")


@pytest.mark.parametrize("params", [
    {"scene": "energy", "energy_view": "week", "basis": "night"},
    {"scene": "energy", "energy_view": "saving", "scope": "控制箱一"},
    {"scene": "night", "sql": "SELECT 1"},
    {"scene": "night", "device": {"circuit_id": "c1"}},
    {"scene": "night", "intent": "downstream"},
])
def test_unsupported_parameters_fail_without_sql(params):
    with pytest.raises(ValueError):
        build_query(LightingRequest.model_validate(params).resolve(NOW))


def test_mcp_auth_and_tool_discovery_use_the_real_app():
    app = RequireToken(create_server(LightingService("http://unused.invalid/mcp", {})).streamable_http_app(), "a" * 48)
    with TestClient(app, base_url="http://127.0.0.1:8012") as client:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        headers = {"Accept": "application/json, text/event-stream"}
        assert client.post("/mcp", json=payload, headers=headers).status_code == 401
        headers["Authorization"] = "Bearer " + "a" * 48
        response = client.post("/mcp", json=payload, headers=headers)
        assert response.status_code == 200
        assert [tool["name"] for tool in response.json()["result"]["tools"]] == ["query_lighting"]


def test_sql_errors_and_truncation_cannot_become_zero_results():
    with pytest.raises(ValueError):
        unwrap_sql(CallToolResult(isError=True, content=[TextContent(type="text", text="database error")]))
    with pytest.raises(ValueError):
        unwrap_sql(CallToolResult(content=[], structuredContent={"result": {"ok": True, "meta": {"truncated": True}, "rows": []}}))


def test_skill_packages_have_no_old_protocol_or_unavailable_command_requirement():
    import yaml
    skills = Path(__file__).resolve().parents[2] / "skills"
    packages = list(skills.glob("lighting-*/SKILL.md"))
    assert len(packages) == 6
    for entry in packages:
        metadata = yaml.safe_load(entry.read_text().split("---", 2)[1])
        assert metadata["name"] == entry.parent.name
        assert len(metadata["description"]) > 30
        assert "query_lighting" in entry.read_text()
        assert "v0.9.1" not in entry.read_text()
        assert (entry.parent / "references/runtime.md").is_file()

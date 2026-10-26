"""Private read-only lighting MCP adapter using the existing SQL MCP."""

import asyncio
from datetime import datetime
import hmac
import json
import logging
import os
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from presenter import present
from queries import build_query, scope_query
from request import LightingRequest

log = logging.getLogger("lighting-query")


def unwrap_sql(response) -> dict:
    if response.isError:
        raise ValueError("SQL MCP 执行失败")
    value = response.structuredContent
    if value is None:
        texts = [item.text for item in response.content if item.type == "text"]
        if len(texts) != 1:
            raise ValueError("SQL MCP 返回不明确")
        value = json.loads(texts[0])
    if isinstance(value, dict) and set(value) == {"result"}:
        value = value["result"]
    if not isinstance(value, dict) or value.get("ok") is not True or value.get("meta", {}).get("truncated"):
        raise ValueError("SQL MCP 返回失败或截断")
    records = value.get("rows", [])
    if len(records) != 1 or "payload" not in records[0]:
        raise ValueError("固定查询未返回唯一结果")
    payload = records[0]["payload"]
    return json.loads(payload) if isinstance(payload, str) else payload


class LightingService:
    def __init__(self, sql_url: str, sql_headers: dict):
        self.sql_url, self.sql_headers = sql_url, sql_headers
        self.slots = asyncio.Semaphore(2)

    async def execute(self, sql: str) -> dict:
        async with streamablehttp_client(self.sql_url, headers=self.sql_headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("sql_query_readonly", {
                    "sql": sql, "max_rows": 1, "request_id": "lighting-" + uuid.uuid4().hex,
                })
                return unwrap_sql(result)

    async def query(self, request: dict) -> dict:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        req = LightingRequest.model_validate(request).resolve(now)
        # Validate supported scope/window before touching a business data source.
        sql = build_query(req)
        async with self.slots:
            async with asyncio.timeout(90):
                lookup = scope_query(req)
                if lookup is not None:
                    matched = await self.execute(lookup)
                    if matched["row_count"] != 1:
                        raise ValueError("范围未精确匹配唯一业务对象,请明确编号或名称")
                data = await self.execute(sql)
                alarm_data = None
                if req.scene in {"night", "rtu"}:
                    alarm_req = req.model_copy(deep=True)
                    alarm_req.scene = "lamp_alarms" if req.scene == "night" else "rtu_alarms"
                    alarm_data = await self.execute(build_query(alarm_req))
                return present(req, data, now, alarm_data)


def create_server(service: LightingService) -> FastMCP:
    server = FastMCP("lighting-query", host="0.0.0.0", port=8012,
                     stateless_http=True, json_response=True, log_level="WARNING",
                     transport_security=TransportSecuritySettings(allowed_hosts=[
                         "lighting-query-mcp:8012", "127.0.0.1:8012", "localhost:8012"]))

    @server.tool()
    async def query_lighting(request: LightingRequest) -> dict:
        """Query real lighting data and display the six prototype result views.

        Load the relevant lighting Skill first. Default scope is 全系统, timezone
        Asia/Shanghai; omit window for the last completed night or full 7/30
        natural days. Pass exact RTU code/name, road name or lamp code as scope;
        RTU/daily scenes accept RTU scope only. Never supply SQL, HTML, computed
        results or raw A2UI. The service reads authorized SQL MCP and creates
        lighting-query/v1 facts. Missing evidence remains explicitly unknown.
        """
        try:
            return await service.query(request.model_dump(mode="json"))
        except Exception as exc:
            # Do not echo SQL MCP errors, credentials, schema or business rows.
            reference = uuid.uuid4().hex[:12]
            log.warning("query_failed reference=%s category=%s", reference, type(exc).__name__)
            raise ValueError(f"照明查询未完成（参考号 {reference}）。请检查时间口径、精确范围及数据源连接；不能据此判断正常。") from None

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(request):
        return JSONResponse({"ok": True, "mode": "readonly"})

    return server


class RequireToken:
    def __init__(self, app, token: str):
        if len(token) < 32:
            raise ValueError("照明适配服务需要独立的强令牌")
        self.app, self.expected = app, ("Bearer " + token).encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            authorization = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(authorization, self.expected):
                await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    import uvicorn

    config = json.loads(Path(os.environ.get("LIGHTING_CONNECTION_FILE", "/run/lighting/connection.json")).read_text())
    server = create_server(LightingService(config["sql_url"], config.get("sql_headers", {})))
    app = RequireToken(server.streamable_http_app(), config["adapter_token"])
    uvicorn.run(app, host="0.0.0.0", port=8012, log_level="warning")

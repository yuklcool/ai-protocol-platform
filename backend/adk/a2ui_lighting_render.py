"""Authorized SQL MCP results → v0.9 Basic fallback + lighting workbench.

The rich table/chart is host-rendered from a declared data model, just like
series artefacts. No custom catalog, model-authored HTML or new channel.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from adk.a2ui_ppa_render import _Tree
from adk.a2ui_result_render import register
from lighting.results import ACTION_NAME, QUERY_TOOL, TITLES, LightingResult, normalize

PROVENANCE_KEY = "temp:_lighting_mcp_server"


def unwrap(result: Any) -> dict:
    """Bounded MCP/result/text envelopes; errors never fall through to data."""
    for _ in range(8):
        if isinstance(result, str):
            result = json.loads(result)
        elif isinstance(result, dict):
            if result.get("isError") or (result.get("error") and "schema_version" not in result):
                raise ValueError("MCP 查询失败,请核对连接与授权后显式重试。")
            if result.get("schema_version") == "lighting-query/v1":
                return result
            if "ok" in result:
                meta = result.get("meta")
                if result["ok"] is not True or not isinstance(meta, dict) or meta.get("truncated") is not False:
                    raise ValueError("SQL 查询失败或返回不完整。")
                rows = result.get("rows")
                if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                    raise ValueError("照明展示查询必须返回唯一 payload。")
                result = rows[0].get("payload")
            elif "structuredContent" in result and result["structuredContent"] is not None:
                result = result["structuredContent"]
            elif set(result) in ({"result"}, {"result", "lighting_presentation_error"}):
                result = result["result"]
            elif isinstance(result.get("content"), list):
                texts = [
                    item["text"]
                    for item in result["content"]
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
                ]
                if len(texts) != 1:
                    raise ValueError("查询返回多个文本块,无法确定结构化结果。")
                result = texts[0]
            else:
                break
        else:
            break
    raise ValueError("查询结果不符合 lighting-query/v1,不能据此判断正常。")


def presentation_feedback(result: Any) -> dict | None:
    """Report contract failures to the querying model without echoing input values."""
    try:
        if len(json.dumps(result, ensure_ascii=False)) > 2_000_000:
            raise ValueError("lighting result exceeds the bounded UI payload")
        normalize(LightingResult.model_validate(unwrap(result)))
    except ValidationError as exc:
        return {
            "errors": exc.errors(include_input=False, include_context=False, include_url=False)[:20],
            "instruction": (
                "SQL 已返回,但照明原型契约校验失败,页面尚未成功展示。"
                "按已加载技能 presentation.schema.json 和 runtime.md 修正本次动态 SQL,"
                "仅通过 sql_query_readonly 重查;不得修改业务事实、猜时区或编造缺失值。"
            ),
        }
    except (ValueError, TypeError, KeyError):
        return {
            "errors": [{"type": "invalid_presentation_payload"}],
            "instruction": "照明原型尚未成功展示。检查原始 SQL 回包、截断状态和唯一 payload,按安全 SQL 技能修正查询。",
        }
    return None


def _root(result: Any, tool_context: Any = None) -> dict:
    try:
        if len(json.dumps(result, ensure_ascii=False)) > 2_000_000:
            raise ValueError("lighting result exceeds the bounded UI payload")
        root = normalize(LightingResult.model_validate(unwrap(result))).model_dump(mode="json")
        root.update(kind="lighting", title=TITLES[root["scene"]])
        state = getattr(tool_context, "state", None)
        root["server_id"] = state.get(PROVENANCE_KEY) if state is not None else None
        return root
    except (ValidationError, ValueError, TypeError, KeyError):
        return {
            "kind": "lighting",
            "title": "照明查询",
            "status": "error",
            "error": "照明查询失败或返回格式不完整,请核对数据源、时间口径及授权后重新查询。",
            "actions": [],
        }


def lighting_to_a2ui(result: Any, tool_context: Any = None) -> list[dict] | None:
    if tool_context is not None:
        from adk.callbacks import A2UI_TOOL_ARGS_STATE_KEY

        sql = tool_context.state.get(A2UI_TOOL_ARGS_STATE_KEY, {}).get("sql", "")
        if not isinstance(sql, str) or "lighting-query/v1" not in sql:
            return None  # Ordinary queries and schema checks do not open a lighting tab.
    root = _root(result, tool_context)
    tree = _Tree()
    children = [tree.text(root["title"], variant="h5")]
    children.append(tree.text(root.get("error") or root["summary"]))
    query = root.get("query")
    if query:
        children.append(
            tree.text(
                f"{query['window']['start']} → {query['window']['end']} · {query['timezone']} · {query['coverage']}"
            )
        )
    for action in root["actions"]:
        children.append(
            tree.button(action["label"], {"event": {"name": ACTION_NAME, "context": {"actionId": action["id"]}}})
        )
    tree.root(children)
    messages = tree.messages()
    messages.append({"version": "v0.9", "updateDataModel": {"surfaceId": "workspace", "path": "/", "value": root}})
    return messages


def _surface(result: Any) -> str:
    try:
        return "lighting:" + LightingResult.model_validate(unwrap(result)).query.id
    except (ValidationError, ValueError, TypeError):
        return "lighting:error"


register(
    lighting_to_a2ui,
    tool_names=[QUERY_TOOL],
    name="lighting_query",
    surface=_surface,
    artifact_meta=lambda result: {"kind": "lighting", "title": _root(result)["title"]},
)

"""仅供 CI 的 HTTP 协议测试服务;不代表外部模型能力,禁止用于产品部署。"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EVIDENCE = []


def lighting_reply(messages):
    """Deterministic model selection; facts still come from the real MCP call."""
    user_index = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), -1)
    if user_index < 0:
        return None
    text = str(messages[user_index].get("content", ""))
    marker = re.search(r"LIGHTING-([a-z_]+)-[a-f0-9]{8}", text)
    action = "run:lighting.query" in text
    if not marker and not action:
        return None
    if any(message.get("role") == "tool" for message in messages[user_index + 1 :]):
        return {
            "role": "assistant",
            "content": "合成查询已返回。请查看历史证据与缺口,不能据此认定生产运行正常。",
        }, "stop"
    scene = marker.group(1) if marker else "night"
    request = {"scene": scene}
    if scene.startswith("energy_"):
        request = {"scene": "energy", "energy_view": scene.removeprefix("energy_")}
    if scene in {"empty", "error"}:
        request = {"scene": "night", "fixture_status": scene}
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_lighting",
                "type": "function",
                "function": {"name": "query_lighting", "arguments": json.dumps({"request": request})},
            }
        ],
    }, "tool_calls"


def plan_reply(messages):
    """Deterministic function calls through the REAL ADK tool/callback pipeline."""
    user_index = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), -1)
    if user_index < 0:
        return None
    marker = re.search(r"TASK-PLAN-(CREATE|UPDATE)-[a-f0-9]{8}", str(messages[user_index].get("content", "")))
    if not marker:
        return None
    if any(message.get("role") == "tool" for message in messages[user_index + 1 :]):
        return {"role": "assistant", "content": f"{marker.group()} 已记录。"}, "stop"

    steps = [
        {"id": "read", "title": "读取资料", "status": "pending"},
        {"id": "check", "title": "核对数据", "status": "pending"},
    ]
    args = {"title": "资料检查计划", "steps": steps}
    if marker.group(1) == "UPDATE":
        plan = None
        for message in reversed(messages[:user_index]):
            if message.get("role") != "tool":
                continue
            try:
                result = json.loads(message.get("content", ""))
                for _ in range(4):
                    if isinstance(result, str):
                        result = json.loads(result)
                    elif isinstance(result, dict) and "result" in result:
                        result = result["result"]
                    else:
                        break
                if isinstance(result, dict) and "task_plan" in result:
                    plan = result["task_plan"]
                    break
            except (ValueError, TypeError):
                continue
        if not plan:
            return {"role": "assistant", "content": "PLAN_FIXTURE_MISSING_HISTORY"}, "stop"
        args.update(plan_id=plan["plan_id"], expected_revision=plan["revision"])
        steps[0]["status"] = "completed"
        steps[1].update(status="needs_input", detail="请补充统计日期")
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{marker.group()}",
                "type": "function",
                "function": {"name": "update_task_plan", "arguments": json.dumps(args, ensure_ascii=False)},
            }
        ],
    }, "tool_calls"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        return self.headers.get("Authorization") == f"Bearer {os.environ['PROBE_API_KEY']}"

    def do_GET(self):
        if self.path == "/evidence":
            return self.reply(EVIDENCE)
        if not self.authorized():
            return self.reply({"error": "unauthorized"}, 401)
        if self.path == "/v1/models":
            return self.reply({"data": [{"id": "setup-chat", "object": "model"}]})
        self.reply({"error": "not found"}, 404)

    def do_POST(self):
        if not self.authorized():
            return self.reply({"error": "unauthorized"}, 401)
        if self.path != "/v1/chat/completions":
            return self.reply({"error": "not found"}, 404)
        size = int(self.headers.get("Content-Length", 0))
        if not 0 < size <= 2_000_000:
            return self.reply({"error": "invalid body"}, 400)
        body = json.loads(self.rfile.read(size))
        if body.get("model") != "setup-chat":
            return self.reply({"error": "unknown model"}, 404)
        tool = (
            body.get("tool_choice", {}).get("function", {}).get("name")
            if isinstance(body.get("tool_choice"), dict)
            else None
        )
        marker = re.search(r"MODEL-SETUP-ROOT-[a-f0-9]{8}", json.dumps(body.get("messages", [])))
        content = marker.group() if marker else "OK"
        message = {"role": "assistant", "content": content}
        finish = "stop"
        if tool == "platform_probe":
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_probe", "type": "function", "function": {"name": tool, "arguments": '{"value":"OK"}'}}
                ],
            }
            finish = "tool_calls"
        plan = plan_reply(body.get("messages", []))
        if plan:
            message, finish = plan
        lighting = lighting_reply(body.get("messages", []))
        if lighting:
            message, finish = lighting
        EVIDENCE.append(
            {
                "model": body["model"],
                "stream": bool(body.get("stream")),
                "probe_tool": tool == "platform_probe",
                "root_marker": marker.group() if marker else None,
                "plan_call": bool(plan and message.get("tool_calls")),
            }
        )
        del EVIDENCE[:-100]
        base = {"id": "chatcmpl-setup", "created": 1, "model": "setup-chat"}
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            first_delta = {**message}
            if message.get("tool_calls"):
                first_delta["tool_calls"] = [
                    {"index": index, **call} for index, call in enumerate(message["tool_calls"])
                ]
            for delta, reason in [(first_delta, None), ({}, finish)]:
                chunk = {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        self.reply(
            {
                **base,
                "object": "chat.completion",
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

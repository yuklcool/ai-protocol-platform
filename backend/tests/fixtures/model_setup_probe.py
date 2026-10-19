"""仅供 CI 的 HTTP 协议测试服务;不代表外部模型能力,禁止用于产品部署。"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EVIDENCE = []


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
        EVIDENCE.append(
            {
                "model": body["model"],
                "stream": bool(body.get("stream")),
                "probe_tool": tool == "platform_probe",
                "root_marker": marker.group() if marker else None,
            }
        )
        del EVIDENCE[:-100]
        base = {"id": "chatcmpl-setup", "created": 1, "model": "setup-chat"}
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for delta, finish in [({"role": "assistant", "content": content}, None), ({}, "stop")]:
                chunk = {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
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

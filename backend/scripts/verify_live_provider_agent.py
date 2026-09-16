#!/usr/bin/env python3
"""Run a real Provider -> Model -> Agent -> MCP Tool Calling acceptance.

This is intentionally NOT a mock test.  It configures the running platform
through its public/admin HTTP APIs, executes the built-in provider/model probes,
creates a real Skill bound to a real MCP server, then sends one real Agent turn
through ``/api/skill/{skill_id}/stream`` and verifies that the model selects and
executes an MCP map tool before producing a final answer.

The provider API key is never accepted on the command line.  The Provider is
registered with the environment reference ``${LIVE_PROVIDER_API_KEY}``; the
backend process must already have that variable in its environment.

The script is safe for a non-empty installation: Provider/model/MCP/Skill ids
are supplied by the caller (the workflow makes them run-unique), and the only
shared record it temporarily touches is the wildcard Tool Permission.  Any
existing wildcard rule is restored in ``finally``.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


API_KEY_REF = "${LIVE_PROVIDER_API_KEY}"
EXPECTED_FINAL_TOKEN = "LIVE_MCP_OK"


class AcceptanceError(RuntimeError):
    pass


@dataclass
class AgentEvidence:
    event_types: list[str]
    tool_calls: list[dict[str, str]]
    tool_result_ids: set[str]
    final_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "eventTypes": self.event_types,
            "toolCalls": self.tool_calls,
            "toolResultIds": sorted(self.tool_result_ids),
            "finalText": self.final_text[-500:],
        }


def _json_or_text(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


class PlatformClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.token = ""

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        expected: tuple[int, ...] = (200,),
        auth: bool = True,
    ) -> tuple[int, Any]:
        headers: dict[str, str] = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.client.request(method, f"{self.base_url}{path}", headers=headers, json=json_body)
        body = _json_or_text(response)
        if response.status_code not in expected:
            raise AcceptanceError(
                f"{method} {path} -> HTTP {response.status_code}, expected {expected}: {body!r}"
            )
        return response.status_code, body

    def login(self, email: str, password: str) -> dict[str, Any]:
        _, body = self.request(
            "POST",
            "/api/auth/login",
            json_body={"email": email, "password": password},
            auth=False,
        )
        if not isinstance(body, dict) or not body.get("access_token"):
            raise AcceptanceError("local-jwt login returned no access_token")
        self.token = str(body["access_token"])
        return body

    def stream_agent(self, skill_id: str, message: str, session_id: str) -> list[dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        payload = {"message": message, "sessionId": session_id}
        events: list[dict[str, Any]] = []
        with self.client.stream(
            "POST",
            f"{self.base_url}/api/skill/{skill_id}/stream",
            headers=headers,
            json=payload,
            timeout=httpx.Timeout(180.0, connect=20.0),
        ) as response:
            if response.status_code != 200:
                raw = response.read().decode("utf-8", errors="replace")
                raise AcceptanceError(f"Agent stream -> HTTP {response.status_code}: {raw[:2000]}")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise AcceptanceError(f"Invalid JSON SSE event: {raw[:500]!r}") from exc
                if isinstance(event, dict):
                    events.append(event)
        return events


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("type") or "")


def _tool_call_id(event: dict[str, Any]) -> str:
    return str(event.get("toolCallId") or event.get("tool_call_id") or "")


def _tool_call_name(event: dict[str, Any]) -> str:
    return str(
        event.get("toolCallName")
        or event.get("tool_call_name")
        or event.get("toolName")
        or event.get("tool_name")
        or ""
    )


def validate_agent_events(events: list[dict[str, Any]]) -> AgentEvidence:
    """Require real tool selection, tool result, final text, and clean terminal."""
    if not events:
        raise AcceptanceError("Agent stream returned no AG-UI events")

    event_types = [_event_type(event) for event in events if _event_type(event)]
    run_errors = [event for event in events if _event_type(event) == "RUN_ERROR"]
    if run_errors:
        raise AcceptanceError(f"Agent emitted RUN_ERROR: {run_errors[-1]!r}")
    if "RUN_FINISHED" not in event_types:
        raise AcceptanceError(f"Agent never emitted RUN_FINISHED; event types={event_types!r}")

    tool_calls: list[dict[str, str]] = []
    map_call_ids: set[str] = set()
    for event in events:
        if _event_type(event) != "TOOL_CALL_START":
            continue
        call_id = _tool_call_id(event)
        name = _tool_call_name(event)
        tool_calls.append({"id": call_id, "name": name})
        if "map" in name.casefold():
            map_call_ids.add(call_id)

    if not map_call_ids:
        raise AcceptanceError(f"Model did not select an MCP map tool; tool calls={tool_calls!r}")

    tool_result_ids = {
        _tool_call_id(event)
        for event in events
        if _event_type(event) == "TOOL_CALL_RESULT" and _tool_call_id(event)
    }
    if not (map_call_ids & tool_result_ids):
        raise AcceptanceError(
            "MCP map Tool Call started but no matching TOOL_CALL_RESULT reached AG-UI; "
            f"map_call_ids={sorted(map_call_ids)!r}, result_ids={sorted(tool_result_ids)!r}"
        )

    chunks: list[str] = []
    for event in events:
        if _event_type(event) != "TEXT_MESSAGE_CONTENT":
            continue
        chunk = event.get("delta")
        if chunk is None:
            chunk = event.get("content")
        if chunk:
            chunks.append(str(chunk))
    final_text = "".join(chunks)
    if EXPECTED_FINAL_TOKEN not in final_text:
        raise AcceptanceError(
            f"Agent completed Tool Calling but final answer did not contain {EXPECTED_FINAL_TOKEN!r}; "
            f"text={final_text[-1000:]!r}"
        )

    return AgentEvidence(
        event_types=event_types,
        tool_calls=tool_calls,
        tool_result_ids=tool_result_ids,
        final_text=final_text,
    )


def _assert_ok(label: str, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or body.get("ok") is not True:
        raise AcceptanceError(f"{label} failed: {body!r}")
    return body


def _permission_body(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(entry.get("type") or "wildcard"),
        "tools": list(entry.get("tools") or []),
        "denied": list(entry.get("denied") or []),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    client = PlatformClient(args.platform_url)
    skill_id = ""
    wildcard_before: dict[str, Any] | None = None
    wildcard_existed = False
    provider_created = False
    model_created = False
    mcp_created = False

    try:
        login = client.login(args.admin_email, args.admin_password)
        group_tags = list((login.get("user") or {}).get("groupTags") or [])
        if "aitana-admin" not in group_tags:
            raise AcceptanceError(f"acceptance user is not a platform admin: groupTags={group_tags!r}")

        # Provider control plane: secret stays server-side as an environment ref.
        _, provider = client.request(
            "PUT",
            f"/api/admin/model-providers/{args.provider_id}",
            json_body={
                "name": args.provider_name,
                "kind": "openai-compatible",
                "base_url": args.provider_base_url,
                "api_key_ref": API_KEY_REF,
                "enabled": True,
            },
        )
        provider_created = True
        if not isinstance(provider, dict) or provider.get("has_api_key") is not True:
            raise AcceptanceError(f"Provider secret reference was not resolved by backend: {provider!r}")

        _, provider_test = client.request("POST", f"/api/admin/model-providers/{args.provider_id}/test")
        _assert_ok("Provider connectivity /models", provider_test)

        _, model = client.request(
            "PUT",
            f"/api/admin/model-providers/models/{args.model_id}",
            json_body={
                "api_name": args.provider_api_model,
                "provider_id": args.provider_id,
                "tier": "default",
                "context_window": args.context_window,
                "max_output_tokens": args.max_output_tokens,
                "description": "real live-provider acceptance model",
                "supports_tools": True,
                "supports_reasoning": args.supports_reasoning,
                "supports_responses_api": args.supports_responses_api,
                "supports_vision": False,
                "residency": "global",
                "enabled": True,
            },
        )
        model_created = True
        if not isinstance(model, dict) or str(model.get("model_id") or "") != args.model_id:
            raise AcceptanceError(f"Dynamic model did not round-trip expected model_id: {model!r}")

        _, completion_probe = client.request("POST", f"/api/admin/model-probes/{args.model_id}/completion")
        _assert_ok("real completion probe", completion_probe)
        _, tool_probe = client.request("POST", f"/api/admin/model-probes/{args.model_id}/tool-calling")
        tool_probe = _assert_ok("real Tool Calling probe", tool_probe)
        probe_tools = tool_probe.get("tool_names") or tool_probe.get("toolNames") or []
        if probe_tools and not any("weather" in str(name).casefold() for name in probe_tools):
            raise AcceptanceError(f"Tool Calling probe called unexpected tools: {probe_tools!r}")

        # Real upstream MCP server on the Compose network.
        _, mcp = client.request(
            "PUT",
            f"/api/admin/mcp-servers/{args.mcp_server_id}",
            json_body={
                "url": args.mcp_upstream_url,
                "transport": "streamable-http",
                "scope": "platform",
                "enabled": True,
                "description": "live Provider Agent MCP acceptance",
            },
        )
        mcp_created = True
        _, health = client.request("POST", f"/api/admin/mcp-servers/{args.mcp_server_id}/health")
        _assert_ok("real MCP initialize health", health)
        _, discovery = client.request("POST", f"/api/admin/mcp-servers/{args.mcp_server_id}/discover")
        discovery = _assert_ok("real MCP discovery", discovery)
        discovered_names = [str(tool.get("name") or "") for tool in discovery.get("tools") or [] if isinstance(tool, dict)]
        if not any("map" in name.casefold() for name in discovered_names):
            raise AcceptanceError(f"real MCP discovery did not expose map tool: {discovered_names!r}")

        # Tool Permission is deny-by-default.  Fresh acceptance DBs have no
        # wildcard rule, but save/restore makes this script safe on a shared env.
        status, existing = client.request(
            "GET",
            "/api/admin/tool-permissions/*",
            expected=(200, 404),
        )
        if status == 200 and isinstance(existing, dict):
            wildcard_existed = True
            wildcard_before = _permission_body(existing)
        client.request(
            "PUT",
            "/api/admin/tool-permissions/*",
            json_body={"type": "wildcard", "tools": ["*"], "denied": []},
        )

        skill_name = args.skill_name
        _, skill = client.request(
            "POST",
            "/api/skills",
            json_body={
                "name": skill_name,
                "description": "Real Provider to MCP Tool Calling acceptance skill",
                "instructions": (
                    "This is an acceptance test. You have an MCP map tool. "
                    "For the user's request you MUST call the map tool exactly as its schema requires. "
                    "Do not answer before the tool result returns. After the tool succeeds, reply with "
                    f"a short sentence that includes the exact token {EXPECTED_FINAL_TOKEN}."
                ),
                "displayName": "Live Provider MCP Acceptance",
                "skillMetadata": {
                    "model": args.model_id,
                    "thinking": "off",
                    "tools": ["mcp"],
                    "toolConfigs": {
                        "mcp": {"servers": [args.mcp_server_id]},
                        "defaults": {"artifacts": False, "memory": False},
                        "a2ui": {"enabled": False},
                    },
                    "enableConfirmation": False,
                },
                "accessControl": {"type": "private"},
            },
            expected=(201,),
        )
        if not isinstance(skill, dict) or not skill.get("skillId"):
            raise AcceptanceError(f"Skill create returned no skillId: {skill!r}")
        skill_id = str(skill["skillId"])

        session_id = f"live-provider-{uuid.uuid4().hex[:12]}"
        events = client.stream_agent(
            skill_id,
            (
                "Use the map tool to show Taipei 101 in Taipei, Taiwan. "
                "You must actually call the available MCP map tool before answering."
            ),
            session_id,
        )
        evidence = validate_agent_events(events)

        return {
            "ok": True,
            "providerId": args.provider_id,
            "modelId": args.model_id,
            "providerApiModel": args.provider_api_model,
            "providerConnectivity": provider_test,
            "completionProbe": completion_probe,
            "toolCallingProbe": tool_probe,
            "mcpServerId": args.mcp_server_id,
            "mcpTools": discovered_names,
            "skillId": skill_id,
            "sessionId": session_id,
            "agent": evidence.as_dict(),
        }
    finally:
        cleanup_errors: list[str] = []

        def _cleanup(method: str, path: str, body: Any = None, expected: tuple[int, ...] = (200, 404)) -> None:
            try:
                client.request(method, path, json_body=body, expected=expected)
            except Exception as exc:  # cleanup must not hide the primary failure
                cleanup_errors.append(f"{method} {path}: {exc}")

        if skill_id:
            _cleanup("DELETE", f"/api/skills/{skill_id}")
        if wildcard_existed and wildcard_before is not None:
            _cleanup("PUT", "/api/admin/tool-permissions/*", wildcard_before)
        else:
            _cleanup("DELETE", "/api/admin/tool-permissions/*")
        if mcp_created:
            _cleanup("DELETE", f"/api/admin/mcp-servers/{args.mcp_server_id}")
        if model_created:
            _cleanup("DELETE", f"/api/admin/model-providers/models/{args.model_id}")
        if provider_created:
            _cleanup("DELETE", f"/api/admin/model-providers/{args.provider_id}")
        client.close()
        if cleanup_errors:
            print(json.dumps({"cleanupWarnings": cleanup_errors}, ensure_ascii=False), file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real Provider -> Agent -> MCP Tool Calling acceptance")
    parser.add_argument("--platform-url", default="http://127.0.0.1:1956")
    parser.add_argument("--admin-email", default="admin@example.com")
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--provider-name", default="Live OpenAI-compatible Provider")
    parser.add_argument("--provider-base-url", required=True)
    parser.add_argument("--provider-api-model", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--context-window", type=int, default=131072)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--supports-reasoning", action="store_true")
    parser.add_argument("--supports-responses-api", action="store_true")
    parser.add_argument("--mcp-server-id", required=True)
    parser.add_argument("--mcp-upstream-url", default="http://mcp-example-map:8080/mcp")
    parser.add_argument("--skill-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

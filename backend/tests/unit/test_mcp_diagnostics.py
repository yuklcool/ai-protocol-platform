"""Hermetic tests for MCP admin diagnostics."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ValidationError

from tools.mcp import diagnostics


def test_ui_resource_uris_detects_html_resources_and_tool_resource_uri() -> None:
    tools = [
        {
            "name": "show-map",
            "_meta": {"ui": {"resourceUri": "ui://maps/result"}},
        }
    ]
    resources = [
        {"uri": "ui://dashboard/home", "mimeType": "text/html;profile=mcp-app"},
        {"uri": "https://example.test/readme", "mimeType": "text/plain"},
        {"uri": "https://example.test/app", "mimeType": "text/html"},
    ]

    assert diagnostics._ui_resource_uris(tools, resources) == [
        "https://example.test/app",
        "ui://dashboard/home",
        "ui://maps/result",
    ]


def test_authentication_error_is_classified() -> None:
    error = diagnostics._classify_exception(RuntimeError("401 Unauthorized"))
    assert error.category == "authentication"


def test_network_error_is_classified() -> None:
    request = httpx.Request("POST", "https://mcp.example.test")
    error = diagnostics._classify_exception(httpx.ConnectError("connection refused", request=request))
    assert error.category == "network"


def test_validation_error_is_classified_as_schema() -> None:
    class Payload(BaseModel):
        count: int

    try:
        Payload(count="not-an-int")
    except ValidationError as exc:
        error = diagnostics._classify_exception(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValidationError")

    assert error.category == "schema"


def test_unknown_error_is_protocol() -> None:
    error = diagnostics._classify_exception(RuntimeError("invalid initialize response"))
    assert error.category == "protocol"

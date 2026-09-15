"""Admin model-level probes for persisted OpenAI-compatible models."""

from __future__ import annotations

import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from admin.scope import PlatformScope
from config.model_provider_registry import MODELS_COLLECTION, PROVIDERS_COLLECTION, resolve_api_key_ref
from db.persistence import get_document

router = APIRouter(prefix="/model-providers/models", tags=["admin-model-providers"])


class ModelProbeRequest(BaseModel):
    mode: Literal["completion", "tool_call"] = "completion"
    prompt: str = "Reply with the word OK only."


class ModelProbeResponse(BaseModel):
    ok: bool
    category: str | None = None
    message: str | None = None
    content: str | None = None
    tool_called: bool | None = None
    latency_ms: int | None = None


@router.post("/{model_id}/test", response_model=ModelProbeResponse)
async def test_dynamic_model(model_id: str, body: ModelProbeRequest, scope: PlatformScope) -> ModelProbeResponse:
    model = get_document(MODELS_COLLECTION, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Dynamic model not found")
    if model.get("enabled", True) is False:
        return ModelProbeResponse(ok=False, category="configuration", message="Model is disabled")

    provider_id = str(model.get("providerId") or "").strip()
    provider = get_document(PROVIDERS_COLLECTION, provider_id) if provider_id else None
    if provider is None or provider.get("enabled", True) is False:
        return ModelProbeResponse(ok=False, category="configuration", message="Model provider is missing or disabled")

    try:
        api_key = resolve_api_key_ref(provider.get("apiKeyRef"))
    except RuntimeError as exc:
        return ModelProbeResponse(ok=False, category="configuration", message=str(exc))

    base_url = str(provider.get("baseUrl") or "").rstrip("/")
    api_name = str(model.get("apiName") or "").strip()
    if not base_url or not api_name:
        return ModelProbeResponse(ok=False, category="configuration", message="Provider base URL or model api_name is missing")

    payload: dict = {
        "model": api_name,
        "messages": [{"role": "user", "content": body.prompt.strip() or "Reply OK."}],
        "max_tokens": 96,
        "temperature": 0,
    }
    if body.mode == "tool_call":
        if model.get("supportsTools", True) is False:
            return ModelProbeResponse(ok=False, category="capability", message="Model is configured with supports_tools=false")
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "platform_probe",
                    "description": "Return a deterministic probe value.",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                },
            }
        ]
        payload["tool_choice"] = {"type": "function", "function": {"name": "platform_probe"}}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return ModelProbeResponse(ok=False, category="network", message=str(exc))

    latency_ms = round((time.monotonic() - started) * 1000)
    if response.status_code in {401, 403}:
        return ModelProbeResponse(ok=False, category="authentication", message=f"HTTP {response.status_code}", latency_ms=latency_ms)
    if response.status_code >= 400:
        return ModelProbeResponse(ok=False, category="protocol", message=f"HTTP {response.status_code}", latency_ms=latency_ms)
    try:
        data = response.json()
        message = data["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return ModelProbeResponse(ok=False, category="schema", message="Invalid chat/completions response schema", latency_ms=latency_ms)

    tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
    if body.mode == "tool_call":
        called = bool(tool_calls) and any(
            isinstance(item, dict) and (item.get("function") or {}).get("name") == "platform_probe"
            for item in tool_calls
        )
        if not called:
            return ModelProbeResponse(ok=False, category="capability", message="Model did not return the requested tool call", tool_called=False, latency_ms=latency_ms)
        return ModelProbeResponse(ok=True, message="Tool calling succeeded", tool_called=True, latency_ms=latency_ms)

    content = message.get("content") if isinstance(message, dict) else None
    return ModelProbeResponse(ok=True, content=str(content) if content is not None else None, tool_called=bool(tool_calls), latency_ms=latency_ms)


__all__ = ["router"]

"""Admin model-level probes for persisted OpenAI-compatible models."""

from __future__ import annotations

import json
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from admin.scope import PlatformScope
from config.model_provider_registry import MODELS_COLLECTION, PROVIDERS_COLLECTION, resolve_api_key_ref
from db.persistence import get_document

router = APIRouter(prefix="/model-providers/models", tags=["admin-model-providers"])


class ModelProbeRequest(BaseModel):
    mode: Literal["completion", "tool_call"] = "completion"
    prompt: str = Field(default="Reply with the word OK only.", max_length=4000)


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

    if str(provider.get("kind") or "openai-compatible") != "openai-compatible":
        return ModelProbeResponse(ok=False, category="configuration", message="Unsupported provider kind")

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

    }
    if model.get("supportsReasoning", False):
        payload["max_completion_tokens"] = 1024
    else:
        payload["max_tokens"] = 96
        payload["temperature"] = 0
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

    probe_payloads = [payload]
    if body.mode == "tool_call":
        # OpenAI-compatible gateways differ on which tool_choice spelling they
        # accept. Keep the success criterion strict (the requested function must
        # actually be returned), but retry request-shape compatibility on 400/422:
        # exact named function -> required -> auto.
        for portable_tool_choice in ("required", "auto"):
            fallback_payload = dict(payload)
            fallback_payload["tool_choice"] = portable_tool_choice
            probe_payloads.append(fallback_payload)

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = None
            for index, candidate_payload in enumerate(probe_payloads):
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=candidate_payload,
                )
                if response.status_code not in {400, 422} or index == len(probe_payloads) - 1:
                    break
    except httpx.RequestError:
        return ModelProbeResponse(ok=False, category="network", message="Could not reach the provider")

    if response is None:  # Defensive: probe_payloads is always non-empty.
        return ModelProbeResponse(ok=False, category="network", message="Provider request was not attempted")

    latency_ms = round((time.monotonic() - started) * 1000)
    if response.status_code in {401, 403}:
        return ModelProbeResponse(ok=False, category="authentication", message=f"HTTP {response.status_code}", latency_ms=latency_ms)
    if not 200 <= response.status_code < 300:
        return ModelProbeResponse(ok=False, category="protocol", message=f"HTTP {response.status_code}", latency_ms=latency_ms)
    try:
        data = response.json()
        message = data["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return ModelProbeResponse(ok=False, category="schema", message="Invalid chat/completions response schema", latency_ms=latency_ms)

    if not isinstance(message, dict):
        return ModelProbeResponse(ok=False, category="schema", message="Invalid message schema", latency_ms=latency_ms)
    tool_calls = message.get("tool_calls")
    if body.mode == "tool_call":
        called = False
        for item in tool_calls if isinstance(tool_calls, list) else []:
            if not isinstance(item, dict) or item.get("type") != "function":
                continue
            function = item.get("function")
            if not isinstance(function, dict) or function.get("name") != "platform_probe":
                continue
            try:
                arguments = json.loads(function.get("arguments", ""))
            except (ValueError, TypeError):
                continue
            if isinstance(arguments, dict) and isinstance(arguments.get("value"), str):
                called = True
                break
        if not called:
            return ModelProbeResponse(ok=False, category="capability", message="Model did not return the requested tool call", tool_called=False, latency_ms=latency_ms)
        return ModelProbeResponse(ok=True, message="Tool calling succeeded", tool_called=True, latency_ms=latency_ms)

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return ModelProbeResponse(ok=False, category="schema", message="No text completion returned", latency_ms=latency_ms)
    # A misconfigured upstream may echo request credentials in its response.
    safe_content = content.replace(api_key, "[REDACTED]") if api_key else content
    return ModelProbeResponse(ok=True, content=safe_content[:4000], tool_called=bool(tool_calls), latency_ms=latency_ms)


__all__ = ["router"]

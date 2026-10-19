"""模型验收记录绑定当前配置与凭证;不保存密钥或探测正文。"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from config.model_provider_registry import MODELS_COLLECTION, PROVIDERS_COLLECTION, resolve_api_key_ref
from db.persistence import get_document, set_document

READINESS_COLLECTION = "model_readiness"
MAX_PROBE_AGE_SECONDS = 86400


def probe_fingerprint(model: dict, provider: dict) -> str:
    try:
        key = resolve_api_key_ref(provider.get("apiKeyRef"))
        credential = hashlib.sha256((key or "").encode()).hexdigest()
    except RuntimeError:
        credential = "missing"
    payload = {
        "provider": {name: provider.get(name) for name in ("kind", "baseUrl", "apiKeyRef", "enabled")},
        "model": {
            name: model.get(name)
            for name in (
                "apiName",
                "providerId",
                "contextWindow",
                "maxOutputTokens",
                "supportsTools",
                "supportsReasoning",
                "supportsResponsesApi",
                "supportsVision",
                "enabled",
            )
        },
        "credential": credential,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def record_probe(model_id: str, mode: str, fingerprint: str, result: dict[str, Any]) -> None:
    safe = {key: result.get(key) for key in ("ok", "category", "message", "latency_ms")}
    set_document(
        READINESS_COLLECTION,
        model_id,
        {
            mode: {**safe, "fingerprint": fingerprint, "tested_at": time.time()},
        },
        merge=True,
    )


def model_readiness(model_id: str, model: dict | None = None, provider: dict | None = None) -> dict:
    model = model if model is not None else get_document(MODELS_COLLECTION, model_id)
    provider = (
        provider if provider is not None else get_document(PROVIDERS_COLLECTION, (model or {}).get("providerId", ""))
    )
    view: dict = {"ready": False, "completion": None, "tool_call": None}
    if not model or not provider or model.get("enabled", True) is False or provider.get("enabled", True) is False:
        return view
    fingerprint = probe_fingerprint(model, provider)
    raw = get_document(READINESS_COLLECTION, model_id) or {}
    now = time.time()
    for mode in ("completion", "tool_call"):
        check = raw.get(mode)
        if not isinstance(check, dict) or check.get("fingerprint") != fingerprint:
            continue
        timestamp = check.get("tested_at")
        if not isinstance(timestamp, (int, float)) or not 0 <= now - timestamp <= MAX_PROBE_AGE_SECONDS:
            continue
        view[mode] = {key: check.get(key) for key in ("ok", "category", "message", "latency_ms", "tested_at")}
    view["ready"] = model.get("supportsTools", True) is not False and all(
        isinstance(view[mode], dict) and view[mode].get("ok") is True for mode in ("completion", "tool_call")
    )
    return view

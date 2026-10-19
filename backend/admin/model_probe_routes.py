"""平台管理员验证模型生成、原生工具调用,通过后明确应用到平台 Root。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from admin.audit import record_admin_action
from admin.scope import PlatformScope
from config.model_provider_registry import (
    MODELS_COLLECTION,
    PROVIDERS_COLLECTION,
    database_registry_enabled,
    resolve_api_key_ref,
)
from config.model_readiness import model_readiness, probe_fingerprint, record_probe
from config.platform_config import PlatformConfigUnavailable, get_platform_config, update_platform_config
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


def _has_requested_probe_tool_call(message: object) -> bool:
    if not isinstance(message, dict):
        return False
    calls = message.get("tool_calls")
    for item in calls if isinstance(calls, list) else []:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        function = item.get("function")
        if _valid_function(function):
            return True
    return False


def _valid_function(function: object) -> bool:
    if not isinstance(function, dict) or function.get("name") != "platform_probe":
        return False
    try:
        arguments = json.loads(function.get("arguments", ""))
    except (ValueError, TypeError):
        return False
    return isinstance(arguments, dict) and isinstance(arguments.get("value"), str)


def _request_payload(model: dict, body: ModelProbeRequest) -> tuple[str, dict]:
    responses = bool(model.get("supportsResponsesApi"))
    prompt = body.prompt.strip() or "Reply OK."
    payload: dict = {
        "model": model["apiName"],
        "input" if responses else "messages": prompt if responses else [{"role": "user", "content": prompt}],
    }
    if responses:
        payload["max_output_tokens"] = model.get("maxOutputTokens") or (1024 if model.get("supportsReasoning") else 128)
    elif model.get("supportsReasoning"):
        payload["max_completion_tokens"] = model.get("maxOutputTokens") or 1024
    else:
        payload.update(max_tokens=model.get("maxOutputTokens") or 96, temperature=0)
    if body.mode == "tool_call":
        function = {
            "name": "platform_probe",
            "description": "Return a probe value.",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        }
        payload["tools"] = (
            [{"type": "function", **function}] if responses else [{"type": "function", "function": function}]
        )
        payload["tool_choice"] = (
            {"type": "function", "name": "platform_probe"}
            if responses
            else {
                "type": "function",
                "function": {"name": "platform_probe"},
            }
        )
    return "/responses" if responses else "/chat/completions", payload


async def _probe(model: dict, provider: dict, body: ModelProbeRequest) -> ModelProbeResponse:
    if model.get("enabled", True) is False or provider.get("enabled", True) is False:
        return ModelProbeResponse(ok=False, category="configuration", message="模型或所属服务已停用,请先启用。")
    if provider.get("kind", "openai-compatible") != "openai-compatible":
        return ModelProbeResponse(ok=False, category="configuration", message="此服务类型不支持模型接入测试。")
    if body.mode == "tool_call" and model.get("supportsTools", True) is False:
        return ModelProbeResponse(
            ok=False, category="capability", message="尚未开启工具调用能力,请编辑模型后重新测试。"
        )
    try:
        api_key = resolve_api_key_ref(provider.get("apiKeyRef"))
    except RuntimeError:
        return ModelProbeResponse(
            ok=False, category="configuration", message="后端密钥变量不存在或为空,请补全部署配置并重建 backend。"
        )
    if not provider.get("baseUrl") or not model.get("apiName"):
        return ModelProbeResponse(
            ok=False, category="configuration", message="API 地址或模型名称为空,请编辑后重新测试。"
        )
    endpoint, payload = _request_payload(model, body)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.monotonic()
    response = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    str(provider["baseUrl"]).rstrip("/") + endpoint, headers=headers, json=payload
                )
            except httpx.RequestError:
                response = None
                if attempt == 2:
                    break
            else:
                if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
            await asyncio.sleep(attempt + 1)
    elapsed = round((time.monotonic() - started) * 1000)
    if response is None:
        return ModelProbeResponse(
            ok=False, category="network", message="无法连接服务,请检查 API 地址、网络或代理配置。", latency_ms=elapsed
        )
    status = response.status_code
    if not 200 <= status < 300:
        category, message = (
            ("authentication", "密钥无效或已过期,请更新后端密钥。")
            if status == 401
            else ("permission", "服务拒绝访问,请检查密钥的模型权限。")
            if status == 403
            else ("model", "模型或接口不存在,请检查 API 地址与模型名称。")
            if status == 404
            else ("rate_limit", "请求受限或额度不足,请检查服务额度后重试。")
            if status == 429
            else ("configuration", "服务不接受当前模型参数,请检查模型能力和接口类型。")
            if status in {400, 422}
            else ("protocol", "模型服务返回异常,请稍后重试或查看服务日志。")
        )
        return ModelProbeResponse(ok=False, category=category, message=f"{message} (HTTP {status})", latency_ms=elapsed)
    try:
        data = response.json()
        if model.get("supportsResponsesApi"):
            output = data["output"]
            if not isinstance(output, list):
                raise ValueError()
            called = any(
                isinstance(item, dict) and item.get("type") == "function_call" and _valid_function(item)
                for item in output
            )
            content = "".join(
                part.get("text", "")
                for item in output
                if isinstance(item, dict) and item.get("type") == "message"
                for part in item.get("content", [])
                if isinstance(part, dict) and part.get("type") == "output_text"
            )
        else:
            message = data["choices"][0]["message"]
            called = _has_requested_probe_tool_call(message)
            content = message.get("content")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return ModelProbeResponse(
            ok=False,
            category="schema",
            message="服务响应不符合所选接口格式,请检查 API 地址和接口类型。",
            latency_ms=elapsed,
        )
    if body.mode == "tool_call":
        return ModelProbeResponse(
            ok=called,
            category=None if called else "capability",
            message="工具调用验证通过。" if called else "模型没有返回要求的结构化工具调用,请确认服务支持工具调用。",
            tool_called=called,
            latency_ms=elapsed,
        )
    if not isinstance(content, str) or not content.strip():
        return ModelProbeResponse(
            ok=False, category="schema", message="模型没有返回有效文本,请检查输出限制与推理参数。", latency_ms=elapsed
        )
    return ModelProbeResponse(
        ok=True, content=(content.replace(api_key, "[REDACTED]") if api_key else content)[:4000], latency_ms=elapsed
    )


@router.get("/current")
def current_root_model(scope: PlatformScope) -> dict:
    from agents.root_runtime import effective_root_config
    from config.effective_models import load_effective_models_config
    from config.models import active_residency_policy
    from config.tenant_models import load_tenant_model_policy
    from db.tenants import get_tenant

    platform = get_platform_config().agent
    tenant_id = scope.user.tenant_id or scope.user.domain
    root = effective_root_config(platform, tenant_id)
    cfg = load_effective_models_config()
    policy = load_tenant_model_policy(tenant_id)

    def resolve(ref: str):
        variants = cfg.tier_variants.get(ref)
        target = variants.get(active_residency_policy(), variants["default"]) if variants else ref
        return next((entry for entry in cfg.models if entry.id == target), None)

    platform_entry = resolve(platform.model)
    tenant_entry = resolve(policy.default_model if root.model == "default" and policy.default_model else root.model)
    tenant = get_tenant(tenant_id)
    return {
        "residency_policy": active_residency_policy(),
        "root_model": platform.model,
        "root_model_id": platform_entry.id if platform_entry else None,
        "root_api_name": platform_entry.api_name if platform_entry else None,
        "tenant_model_id": tenant_entry.id if tenant_entry else None,
        "tenant_api_name": tenant_entry.api_name if tenant_entry else None,
        "tenant_allowed": bool(
            tenant
            and not tenant.disabled
            and tenant_entry
            and policy.allows(tenant_entry.id)
            and (active_residency_policy() != "eu-strict" or tenant_entry.residency == "eu")
        ),
    }


@router.post("/{model_id}/test", response_model=ModelProbeResponse)
async def test_dynamic_model(model_id: str, body: ModelProbeRequest, scope: PlatformScope) -> ModelProbeResponse:
    model = get_document(MODELS_COLLECTION, model_id)
    if model is None:
        raise HTTPException(404, "模型不存在。")
    provider = get_document(PROVIDERS_COLLECTION, str(model.get("providerId") or ""))
    if provider is None:
        return ModelProbeResponse(ok=False, category="configuration", message="所属模型服务不存在,请重新选择服务。")
    fingerprint = probe_fingerprint(model, provider)
    result = await _probe(model, provider, body)
    record_probe(model_id, body.mode, fingerprint, result.model_dump())
    return result


@router.post("/{model_id}/use")
def use_root_model(model_id: str, scope: PlatformScope) -> dict:
    if not database_registry_enabled():
        raise HTTPException(409, "当前使用配置文件管理模型,请先启用数据库模型管理。")
    from config.models import active_residency_policy

    model = get_document(MODELS_COLLECTION, model_id)
    if model and active_residency_policy() == "eu-strict" and model.get("residency") != "eu":
        raise HTTPException(
            409, "此部署仅允许欧盟区域模型。请选择实际在欧盟处理数据的服务并核对模型区域,不能仅改标签绕过。"
        )
    if not model_readiness(model_id)["ready"]:
        raise HTTPException(409, "当前配置尚未通过 24 小时内的普通生成和工具调用测试,请重新测试后使用。")
    try:
        before = get_platform_config()
        agent = before.agent.model_copy(update={"model": model_id})
        updated = update_platform_config({"agent": agent.model_dump(by_alias=True)}, updated_by=scope.user.uid)
    except PlatformConfigUnavailable as exc:
        raise HTTPException(503, "无法读取或保存平台 Root 配置,请稍后重试。") from exc
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="use_root_model",
        target=model_id,
        before={"model": before.agent.model},
        after={"model": updated.agent.model},
    )
    return {"root_model": updated.agent.model}


__all__ = ["router"]

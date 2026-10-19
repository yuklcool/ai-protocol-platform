"""Admin control plane for dynamic model providers and model registry entries.

Issue #10, slice 1. YAML/env remain bootstrap/GitOps configuration. These
routes manage database-backed overrides without ever accepting or returning a
plaintext API key. Provider credentials are environment secret references such
as ``${DEEPSEEK_API_KEY}``.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from admin.audit import record_admin_action
from admin.scope import PlatformScope
from config.model_provider_registry import (
    MODELS_COLLECTION,
    PROVIDERS_COLLECTION,
    database_registry_enabled,
    provider_view,
    resolve_api_key_ref,
)
from db.persistence import delete_document, get_document, query_documents, set_document

router = APIRouter(prefix="/model-providers", tags=["admin-model-providers"])
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENV_REF_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")


class ProviderWrite(BaseModel):
    name: str
    kind: Literal["openai-compatible"] = "openai-compatible"
    base_url: str
    api_key_ref: str | None = None
    enabled: bool = True


class ProviderView(BaseModel):
    provider_id: str
    name: str
    kind: str
    base_url: str
    api_key_ref: str | None = None
    has_api_key: bool = False
    enabled: bool = True


class ProviderTestView(BaseModel):
    ok: bool
    category: str | None = None
    message: str | None = None
    model_count: int | None = None
    models: list[str] = Field(default_factory=list)


class DynamicModelWrite(BaseModel):
    api_name: str = Field(min_length=1, max_length=256)
    provider_id: str
    tier: Literal["default", "smart", "fast"] = "default"
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    description: str = ""
    input_cost_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_cost_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    supports_tools: bool = True
    supports_reasoning: bool = False
    supports_responses_api: bool = False
    supports_vision: bool = False
    residency: Literal["eu", "us", "global"] = "global"
    enabled: bool = True


class DynamicModelView(DynamicModelWrite):
    model_id: str
    readiness: dict = Field(default_factory=dict)


def _id(value: str, label: str) -> str:
    normalized = value.strip()
    if not _PROVIDER_ID_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"{label} 只能包含字母、数字、点、下划线或短横线。")
    return normalized


def _base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="API 根地址必须使用 http 或 https 协议。")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/").endswith(("/chat/completions", "/responses", "/models"))
    ):
        raise HTTPException(
            422, "请填写不含密钥或查询参数的 API 根地址,不要填写 /chat/completions、/responses 或 /models 完整接口。"
        )
    return normalized


def _api_key_ref(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if not _ENV_REF_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail="密钥配置只能使用 ${ENV_VAR} 变量引用,不能填写明文密钥。",
        )
    return normalized


def _audit_provider(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    safe = dict(data)
    safe["apiKeyRef"] = "<configured>" if safe.get("apiKeyRef") else None
    return safe


def _model_view(model_id: str, data: dict[str, Any]) -> DynamicModelView:
    from config.model_readiness import model_readiness

    return DynamicModelView(
        model_id=model_id,
        readiness=model_readiness(model_id, data),
        api_name=str(data.get("apiName") or ""),
        provider_id=str(data.get("providerId") or ""),
        tier=str(data.get("tier") or "default"),
        context_window=int(data.get("contextWindow") or 1),
        max_output_tokens=int(data.get("maxOutputTokens") or 1),
        description=str(data.get("description") or ""),
        input_cost_per_million=data.get("inputCostPerMillion"),
        output_cost_per_million=data.get("outputCostPerMillion"),
        supports_tools=data.get("supportsTools", True) is not False,
        supports_reasoning=bool(data.get("supportsReasoning", False)),
        supports_responses_api=bool(data.get("supportsResponsesApi", False)),
        supports_vision=bool(data.get("supportsVision", False)),
        residency=str(data.get("residency") or "global"),
        enabled=data.get("enabled", True) is not False,
    )


@router.get("", response_model=list[ProviderView])
def list_providers(scope: PlatformScope) -> list[ProviderView]:
    result: list[ProviderView] = []
    for raw in query_documents(PROVIDERS_COLLECTION):
        data = dict(raw)
        provider_id = str(data.pop("__id", ""))
        if provider_id:
            result.append(ProviderView(**provider_view(provider_id, data)))
    return sorted(result, key=lambda item: item.provider_id.casefold())


@router.put("/{provider_id}", response_model=ProviderView)
def upsert_provider(provider_id: str, body: ProviderWrite, scope: PlatformScope) -> ProviderView:
    if not database_registry_enabled():
        raise HTTPException(409, "当前使用配置文件管理模型,不能在此新增或修改。")
    provider_id = _id(provider_id, "provider_id")
    before = get_document(PROVIDERS_COLLECTION, provider_id)
    ref = _api_key_ref(body.api_key_ref)
    data = {
        "name": body.name.strip() or provider_id,
        "kind": body.kind,
        "baseUrl": _base_url(body.base_url),
        "apiKeyRef": ref,
        "enabled": body.enabled,
    }
    set_document(PROVIDERS_COLLECTION, provider_id, data, merge=False)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="upsert_model_provider",
        target=provider_id,
        before=_audit_provider(before),
        after=_audit_provider(data),
    )
    return ProviderView(**provider_view(provider_id, data))


@router.delete("/{provider_id}", response_model=ProviderView)
def delete_provider(provider_id: str, scope: PlatformScope) -> ProviderView:
    provider_id = _id(provider_id, "provider_id")
    data = get_document(PROVIDERS_COLLECTION, provider_id)
    if data is None:
        raise HTTPException(status_code=404, detail="模型服务不存在。")
    # Refuse to orphan dynamic models.
    references = [row for row in query_documents(MODELS_COLLECTION) if str(row.get("providerId") or "") == provider_id]
    if references:
        raise HTTPException(status_code=409, detail="此服务仍有模型,请先删除所属模型。")
    delete_document(PROVIDERS_COLLECTION, provider_id)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="delete_model_provider",
        target=provider_id,
        before=_audit_provider(data),
        after=None,
    )
    return ProviderView(**provider_view(provider_id, data))


@router.post("/{provider_id}/test", response_model=ProviderTestView)
async def test_provider(provider_id: str, scope: PlatformScope) -> ProviderTestView:
    provider_id = _id(provider_id, "provider_id")
    data = get_document(PROVIDERS_COLLECTION, provider_id)
    if data is None:
        raise HTTPException(status_code=404, detail="模型服务不存在。")
    if data.get("enabled", True) is False:
        return ProviderTestView(ok=False, category="configuration", message="模型服务已停用,请启用后重试。")
    try:
        key = resolve_api_key_ref(data.get("apiKeyRef"))
    except RuntimeError:
        return ProviderTestView(
            ok=False, category="configuration", message="后端密钥变量不存在或为空,请补全部署配置并重建 backend。"
        )

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    url = str(data.get("baseUrl") or "").rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError:
        return ProviderTestView(ok=False, category="network", message="无法连接服务,请检查 API 地址、网络或代理配置。")
    if response.status_code in {401, 403}:
        return ProviderTestView(
            ok=False,
            category="authentication",
            message=f"服务拒绝认证或授权,请检查后端密钥和模型权限。(HTTP {response.status_code})",
        )
    if not 200 <= response.status_code < 300:
        return ProviderTestView(
            ok=False,
            category="protocol",
            message=f"读取模型列表失败,可手动填写名称后测试。(HTTP {response.status_code})",
        )
    try:
        payload = response.json()
    except ValueError:
        return ProviderTestView(
            ok=False, category="protocol", message="服务返回的模型列表不是有效 JSON,可手动填写模型名称。"
        )
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return ProviderTestView(
            ok=False, category="protocol", message="服务未返回标准模型列表,请手动填写模型名称并测试。"
        )
    ids = list(
        dict.fromkeys(
            item["id"].strip()
            for item in models
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item["id"].strip()
            and (not key or key not in item["id"])
        )
    )
    if models and not ids:
        return ProviderTestView(
            ok=False, category="protocol", message="模型列表没有有效名称,请手动填写模型名称并测试。"
        )
    return ProviderTestView(ok=True, model_count=len(ids), models=ids[:1000])


@router.get("/models", response_model=list[DynamicModelView])
def list_dynamic_models(scope: PlatformScope) -> list[DynamicModelView]:
    result: list[DynamicModelView] = []
    for raw in query_documents(MODELS_COLLECTION):
        data = dict(raw)
        model_id = str(data.pop("__id", ""))
        if model_id:
            result.append(_model_view(model_id, data))
    return sorted(result, key=lambda item: item.model_id.casefold())


@router.put("/models/{model_id}", response_model=DynamicModelView)
def upsert_dynamic_model(model_id: str, body: DynamicModelWrite, scope: PlatformScope) -> DynamicModelView:
    if not database_registry_enabled():
        raise HTTPException(409, "当前使用配置文件管理模型,不能在此新增或修改。")
    if body.max_output_tokens > body.context_window:
        raise HTTPException(422, "最大输出不能超过上下文长度。")
    model_id = _id(model_id, "model_id")
    provider_id = _id(body.provider_id, "provider_id")
    provider = get_document(PROVIDERS_COLLECTION, provider_id)
    if provider is None:
        raise HTTPException(status_code=422, detail="所属模型服务不存在。")
    before = get_document(MODELS_COLLECTION, model_id)
    pricing_fields = {"input_cost_per_million", "output_cost_per_million"}
    if body.model_fields_set & pricing_fields and (
        (body.input_cost_per_million is None) != (body.output_cost_per_million is None)
    ):
        raise HTTPException(422, "请同时填写输入和输出价格,或同时留空。")
    data = {
        "apiName": body.api_name.strip(),
        "providerId": provider_id,
        "tier": body.tier,
        "contextWindow": body.context_window,
        "maxOutputTokens": body.max_output_tokens,
        "description": body.description.strip(),
        "inputCostPerMillion": body.input_cost_per_million
        if body.model_fields_set & pricing_fields
        else (before or {}).get("inputCostPerMillion"),
        "outputCostPerMillion": body.output_cost_per_million
        if body.model_fields_set & pricing_fields
        else (before or {}).get("outputCostPerMillion"),
        "supportsTools": body.supports_tools,
        "supportsReasoning": body.supports_reasoning,
        "supportsResponsesApi": body.supports_responses_api,
        "supportsVision": body.supports_vision,
        "residency": body.residency,
        "enabled": body.enabled,
    }
    if not data["apiName"]:
        raise HTTPException(status_code=422, detail="请填写服务中的模型名称。")
    set_document(MODELS_COLLECTION, model_id, data, merge=False)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="upsert_dynamic_model",
        target=model_id,
        before=before,
        after=data,
    )
    return _model_view(model_id, data)


@router.delete("/models/{model_id}", response_model=DynamicModelView)
def delete_dynamic_model(model_id: str, scope: PlatformScope) -> DynamicModelView:
    model_id = _id(model_id, "model_id")
    data = get_document(MODELS_COLLECTION, model_id)
    if data is None:
        raise HTTPException(status_code=404, detail="模型不存在。")
    from config.model_provider_registry import registry_settings
    from config.model_readiness import READINESS_COLLECTION
    from config.platform_config import get_platform_config

    root = get_platform_config().agent
    settings = registry_settings()
    if (
        root.model == model_id
        or settings.get("platformDefault") == model_id
        or model_id in (settings.get("tierDefaults") or {}).values()
    ):
        raise HTTPException(409, "此模型仍用于平台 Root 或高级路由,请先替换相应选择再删除。")
    delete_document(MODELS_COLLECTION, model_id)
    delete_document(READINESS_COLLECTION, model_id)
    record_admin_action(
        actor_uid=scope.user.uid,
        actor_email=scope.user.email or "",
        actor_tenant_id=scope.user.tenant_id or "",
        action="delete_dynamic_model",
        target=model_id,
        before=data,
        after=None,
    )
    return _model_view(model_id, data)


__all__ = ["router"]

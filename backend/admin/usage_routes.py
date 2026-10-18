"""Access-scoped durable usage and current tenant quota summary."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from admin.scope import Scope
from budget.tenant_repository_enforcer import LEDGER_COLLECTION, TenantRepositoryBudgetEnforcer
from db.persistence import get_repository
from db.tenants import TenantConfig, TenantDirectory
from observability.usage import COLLECTION

router = APIRouter(prefix="/usage", tags=["admin-usage"])


@router.get("")
def usage_summary(scope: Scope, tenant_id: str = "", days: int = Query(default=30, ge=1, le=366)) -> dict[str, Any]:
    if tenant_id:
        scope.assert_may_tenant(tenant_id)
    elif not scope.is_platform and not scope.tenant_ids:
        raise HTTPException(403, "Tenant scope is required")
    repo = get_repository()
    since = time.time() - days * 86400
    tenants = TenantDirectory(repo).list()
    # Include attributed usage from an older installation whose tenant has not
    # yet been registered. Never infer a tenant from a UID or email domain.
    scopes = [tenant_id] if tenant_id else [None] if scope.is_platform else list(scope.tenant_ids or [])
    usage_rows = []
    for key in scopes:
        filters = [("createdAt", ">=", since)]
        if key:
            filters.append(("tenantId", "==", key))
        usage_rows.extend(repo.query_documents(COLLECTION, filters=filters, limit=None))
    usage_rows = [row for row in usage_rows if scope.may_tenant(str(row.get("tenantId") or ""))]
    known_ids = {tenant.tenant_id for tenant in tenants}
    for row in usage_rows:
        key = str(row.get("tenantId") or "")
        if key not in known_ids:
            tenants.append(TenantConfig(tenantId=key))
            known_ids.add(key)
    allowed = [
        tenant
        for tenant in tenants
        if (not tenant_id or tenant.tenant_id == tenant_id) and scope.may_tenant(tenant.tenant_id)
    ]
    summaries = []
    total = {"calls": 0, "inputTokens": 0, "outputTokens": 0, "estimatedCostUsd": 0.0, "unpricedCalls": 0}
    by_model: dict[str, dict[str, Any]] = {}
    for tenant in allowed:
        rows = [row for row in usage_rows if row.get("tenantId") == tenant.tenant_id]
        stats = {
            "calls": len(rows),
            "inputTokens": sum(int(row.get("inputTokens") or 0) for row in rows),
            "outputTokens": sum(int(row.get("outputTokens") or 0) for row in rows),
            "estimatedCostUsd": sum(float(row.get("estimatedCostUsd") or 0) for row in rows),
            "unpricedCalls": sum(not row.get("pricingKnown", False) for row in rows),
        }
        for key, value in stats.items():
            total[key] += value
        for row in rows:
            model = str(row.get("modelId") or "unknown")
            item = by_model.setdefault(
                model, {"modelId": model, "calls": 0, "inputTokens": 0, "outputTokens": 0, "estimatedCostUsd": 0.0}
            )
            item["calls"] += 1
            for key in ("inputTokens", "outputTokens", "estimatedCostUsd"):
                item[key] += row.get(key) or 0
        period = str(tenant.quota.get("llmBudgetPeriod") or "monthly")
        period_key = TenantRepositoryBudgetEnforcer._period_key(time.time(), period)
        ledger = repo.query_documents(
            LEDGER_COLLECTION,
            filters=[("tenantId", "==", tenant.tenant_id), ("periodKey", "==", period_key)],
            limit=None,
        )
        charged = sum(float(row.get("chargedCostUsd") or 0) for row in ledger)
        summaries.append(
            {
                "tenantId": tenant.tenant_id,
                "label": tenant.display_name or tenant.tenant_id,
                **stats,
                "quotaUsd": tenant.quota.get("llmBudgetUsd"),
                "period": period,
                "chargedUsd": charged,
                "heldUsd": sum(float(row.get("chargedCostUsd") or 0) for row in ledger if row.get("status") == "held"),
            }
        )
    return {
        "days": days,
        "totals": total,
        "tenants": summaries,
        "models": list(by_model.values()),
        "costBasis": "estimated",
        "historyStartsWithAccounting": True,
    }

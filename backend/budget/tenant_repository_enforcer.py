"""Repository-backed tenant LLM budget enforcement.

This implementation is intended for self-host deployments that already use the
platform Repository (PostgreSQL by default).  It keeps the existing pluggable
BudgetEnforcer contract and is explicitly opt-in via BUDGET_ENFORCER.

Tenant quota schema (all optional, under tenants/{tenant_id}.quota):

    {
      "llmBudgetUsd": 25.0,
      "llmBudgetPeriod": "monthly",
      "llmBudgetSoftThreshold": 0.8
    }

A missing/non-positive cap is treated as unconfigured (allow, with no ledger
charge), preserving the historical opt-in semantics.

The ledger uses one document per (tenant, period, invocation).  A consult writes
its projected hold *before* summing the period, so concurrent requests are
conservative: overlapping calls see each other's holds instead of both slipping
through a read-before-write race.  record() reconciles the hold to actual cost.
"""

from __future__ import annotations

import calendar
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from budget.enforcer import BudgetConsultation, BudgetDecision
from db.repository import Repository
from db.tenants import TenantDirectory

logger = logging.getLogger("budget")

LEDGER_COLLECTION = "tenant_budget_ledger"
_ALLOWED_PERIODS = frozenset({"daily", "weekly", "monthly"})


@dataclass
class TenantRepositoryBudgetEnforcer:
    repository: Repository
    default_soft_threshold: float = 0.8
    default_period: str = "monthly"

    def _tenant_policy(self, tenant_id: str) -> tuple[float, float, str] | None:
        tenant = TenantDirectory(self.repository).get(tenant_id)
        if tenant is None or tenant.disabled:
            return None

        quota = tenant.quota or {}
        try:
            cap = float(quota.get("llmBudgetUsd") or 0.0)
        except (TypeError, ValueError):
            cap = 0.0
        if cap <= 0:
            return (0.0, self.default_soft_threshold, self.default_period)

        try:
            soft = float(quota.get("llmBudgetSoftThreshold", self.default_soft_threshold))
        except (TypeError, ValueError):
            soft = self.default_soft_threshold
        soft = min(1.0, max(0.0, soft))

        period = str(quota.get("llmBudgetPeriod") or self.default_period).strip().lower()
        if period not in _ALLOWED_PERIODS:
            period = self.default_period

        return (cap, soft, period)

    @staticmethod
    def _period_key(ts: float, period: str) -> str:
        dt = datetime.fromtimestamp(ts, tz=UTC)
        if period == "daily":
            return dt.strftime("%Y-%m-%d")
        if period == "weekly":
            iso_year, iso_week, _ = dt.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"
        return dt.strftime("%Y-%m")

    @staticmethod
    def _next_period_start(ts: float, period: str) -> datetime:
        dt = datetime.fromtimestamp(ts, tz=UTC)
        if period == "daily":
            target = (dt + timedelta(days=1)).date()
            return datetime(target.year, target.month, target.day, tzinfo=UTC)
        if period == "weekly":
            days_until_monday = (7 - dt.weekday()) % 7 or 7
            target = (dt + timedelta(days=days_until_monday)).date()
            return datetime(target.year, target.month, target.day, tzinfo=UTC)
        last_day = calendar.monthrange(dt.year, dt.month)[1]
        target = (dt.replace(day=last_day) + timedelta(days=1)).date()
        return datetime(target.year, target.month, target.day, tzinfo=UTC)

    @classmethod
    def _period_end_iso(cls, ts: float, period: str) -> str:
        return cls._next_period_start(ts, period).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def _seconds_until_period_end(cls, ts: float, period: str) -> int:
        return int(max(0.0, cls._next_period_start(ts, period).timestamp() - ts))

    @staticmethod
    def _ledger_id(request: BudgetConsultation, period_key: str) -> str:
        raw = f"{request.identity_value}\0{period_key}\0{request.invocation_id}".encode()
        return hashlib.sha256(raw).hexdigest()

    async def consult(self, request: BudgetConsultation) -> BudgetDecision:
        now = time.time()
        policy = self._tenant_policy(request.identity_value)
        if policy is None:
            return BudgetDecision(
                action="block",
                remaining_usd=0.0,
                period_end=None,
                message=f"Tenant budget configuration is unavailable for {request.identity_value}.",
                retry_after_seconds=None,
            )

        cap, soft_threshold, period = policy
        period_key = self._period_key(now, period)
        period_end = self._period_end_iso(now, period)

        if cap <= 0.0:
            logger.warning(
                "budget.tenant_cap_unconfigured",
                extra={
                    "tenant_id": request.identity_value,
                    "skill_id": request.skill_id,
                },
            )
            return BudgetDecision(
                action="allow",
                remaining_usd=None,
                period_end=period_end,
                message=None,
                retry_after_seconds=None,
            )

        ledger_id = self._ledger_id(request, period_key)
        existing = self.repository.get_document(LEDGER_COLLECTION, ledger_id)
        if existing is not None:
            return BudgetDecision(
                action=str(existing.get("decision") or "allow"),
                remaining_usd=existing.get("remainingUsd"),
                period_end=str(existing.get("periodEnd") or period_end),
                message=existing.get("message"),
                retry_after_seconds=existing.get("retryAfterSeconds"),
            )

        # Write the hold before summing. This makes concurrent calls
        # conservative across processes backed by the shared repository.
        self.repository.set_document(
            LEDGER_COLLECTION,
            ledger_id,
            {
                "tenantId": request.identity_value,
                "periodKey": period_key,
                "period": period,
                "invocationId": request.invocation_id,
                "skillId": request.skill_id,
                "modelId": request.model_id,
                "projectedCostUsd": request.projected_cost_usd,
                "chargedCostUsd": request.projected_cost_usd,
                "actualCostUsd": None,
                "status": "held",
                "createdAt": now,
                "updatedAt": now,
            },
        )

        rows = self.repository.query_documents(
            LEDGER_COLLECTION,
            filters=[
                ("tenantId", "==", request.identity_value),
                ("periodKey", "==", period_key),
            ],
            limit=None,
        )
        total = sum(float(row.get("chargedCostUsd") or 0.0) for row in rows)
        remaining = max(0.0, cap - total)

        if total >= cap:
            decision = BudgetDecision(
                action="block",
                remaining_usd=0.0,
                period_end=period_end,
                message=(
                    f"Budget exhausted for tenant {request.identity_value} this {period} period. "
                    f"Resets at {period_end}."
                ),
                retry_after_seconds=self._seconds_until_period_end(now, period),
            )
        elif total >= cap * soft_threshold:
            decision = BudgetDecision(
                action="warn",
                remaining_usd=remaining,
                period_end=period_end,
                message=(
                    f"Tenant {request.identity_value} has used "
                    f"{int(total / cap * 100)}% of this {period} LLM budget."
                ),
                retry_after_seconds=None,
            )
        else:
            decision = BudgetDecision(
                action="allow",
                remaining_usd=remaining,
                period_end=period_end,
                message=None,
                retry_after_seconds=None,
            )

        self.repository.update_document(
            LEDGER_COLLECTION,
            ledger_id,
            {
                "decision": decision.action,
                "remainingUsd": decision.remaining_usd,
                "periodEnd": decision.period_end,
                "message": decision.message,
                "retryAfterSeconds": decision.retry_after_seconds,
                "updatedAt": time.time(),
            },
        )
        return decision

    async def record(self, request: BudgetConsultation, actual_cost_usd: float) -> None:
        policy = self._tenant_policy(request.identity_value)
        if policy is None:
            return
        cap, _soft_threshold, period = policy
        if cap <= 0.0:
            return

        period_key = self._period_key(time.time(), period)
        ledger_id = self._ledger_id(request, period_key)
        existing = self.repository.get_document(LEDGER_COLLECTION, ledger_id)
        if existing is None:
            return

        self.repository.update_document(
            LEDGER_COLLECTION,
            ledger_id,
            {
                "actualCostUsd": max(0.0, float(actual_cost_usd)),
                "chargedCostUsd": max(0.0, float(actual_cost_usd)),
                "status": "recorded",
                "updatedAt": time.time(),
            },
        )


__all__ = ["LEDGER_COLLECTION", "TenantRepositoryBudgetEnforcer"]

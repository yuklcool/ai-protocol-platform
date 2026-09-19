from __future__ import annotations

import pytest

from budget.enforcer import BudgetConsultation
from budget.tenant_repository_enforcer import LEDGER_COLLECTION, TenantRepositoryBudgetEnforcer
from db.repositories.memory import MemoryRepository
from db.tenants import TenantConfig, TenantDirectory


def _tenant(repo: MemoryRepository, tenant_id: str, *, cap: float | None, period: str = "monthly") -> None:
    quota = {}
    if cap is not None:
        quota = {
            "llmBudgetUsd": cap,
            "llmBudgetPeriod": period,
            "llmBudgetSoftThreshold": 0.8,
        }
    TenantDirectory(repo).put(
        TenantConfig(
            tenantId=tenant_id,
            displayName=tenant_id,
            storageNamespace=tenant_id,
            quota=quota,
        )
    )


def _request(tenant_id: str, invocation: str, projected: float) -> BudgetConsultation:
    return BudgetConsultation(
        identity_value=tenant_id,
        skill_id="tenant-budget-skill",
        model_id="openai/gpt-5.6-luna",
        projected_cost_usd=projected,
        invocation_id=invocation,
    )


@pytest.mark.asyncio
async def test_tenant_b_bucket_is_independent_when_tenant_a_reaches_cap() -> None:
    repo = MemoryRepository()
    _tenant(repo, "tenant-a", cap=1.0)
    _tenant(repo, "tenant-b", cap=1.0)
    enforcer = TenantRepositoryBudgetEnforcer(repo)

    a1 = await enforcer.consult(_request("tenant-a", "a-1", 0.60))
    a2 = await enforcer.consult(_request("tenant-a", "a-2", 0.50))
    b1 = await enforcer.consult(_request("tenant-b", "b-1", 0.60))

    assert a1.action == "allow"
    assert a2.action == "block"
    assert b1.action == "allow"

    rows_a = repo.query_documents(LEDGER_COLLECTION, filters=[("tenantId", "==", "tenant-a")])
    rows_b = repo.query_documents(LEDGER_COLLECTION, filters=[("tenantId", "==", "tenant-b")])
    assert len(rows_a) == 2
    assert len(rows_b) == 1
    assert sum(float(row["chargedCostUsd"]) for row in rows_a) == pytest.approx(0.60)
    assert sum(float(row["chargedCostUsd"]) for row in rows_b) == pytest.approx(0.60)


@pytest.mark.asyncio
async def test_record_reconciles_shared_repository_hold_to_actual_cost() -> None:
    repo = MemoryRepository()
    _tenant(repo, "tenant-a", cap=1.0)
    enforcer = TenantRepositoryBudgetEnforcer(repo)
    request = _request("tenant-a", "a-1", 0.60)

    assert (await enforcer.consult(request)).action == "allow"
    await enforcer.record(request, actual_cost_usd=0.10)

    rows = repo.query_documents(LEDGER_COLLECTION, filters=[("tenantId", "==", "tenant-a")])
    assert len(rows) == 1
    assert rows[0]["status"] == "recorded"
    assert rows[0]["projectedCostUsd"] == pytest.approx(0.60)
    assert rows[0]["actualCostUsd"] == pytest.approx(0.10)
    assert rows[0]["chargedCostUsd"] == pytest.approx(0.10)

    # A second 0.70 hold sees the reconciled 0.10, not the original 0.60.
    second = await enforcer.consult(_request("tenant-a", "a-2", 0.70))
    assert second.action == "allow"


@pytest.mark.asyncio
async def test_duplicate_invocation_is_idempotent() -> None:
    repo = MemoryRepository()
    _tenant(repo, "tenant-a", cap=1.0)
    enforcer = TenantRepositoryBudgetEnforcer(repo)
    request = _request("tenant-a", "same-invocation", 0.25)

    first = await enforcer.consult(request)
    second = await enforcer.consult(request)

    assert first.action == second.action == "allow"
    rows = repo.query_documents(LEDGER_COLLECTION, filters=[("tenantId", "==", "tenant-a")])
    assert len(rows) == 1
    assert rows[0]["chargedCostUsd"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_unconfigured_tenant_cap_allows_without_creating_ledger() -> None:
    repo = MemoryRepository()
    _tenant(repo, "tenant-a", cap=None)
    enforcer = TenantRepositoryBudgetEnforcer(repo)

    decision = await enforcer.consult(_request("tenant-a", "a-1", 100.0))

    assert decision.action == "allow"
    assert decision.remaining_usd is None
    assert repo.query_documents(LEDGER_COLLECTION) == []


@pytest.mark.asyncio
async def test_missing_tenant_fails_closed_when_repository_enforcer_is_selected() -> None:
    repo = MemoryRepository()
    enforcer = TenantRepositoryBudgetEnforcer(repo)

    decision = await enforcer.consult(_request("missing-tenant", "m-1", 0.01))

    assert decision.action == "block"
    assert decision.remaining_usd == 0.0
    assert "unavailable" in (decision.message or "").lower()


@pytest.mark.asyncio
async def test_blocked_attempt_does_not_consume_remaining_budget():
    repo = MemoryRepository()
    _tenant(repo, "tenant-a", cap=1.0)
    enforcer = TenantRepositoryBudgetEnforcer(repo)
    rejected = _request("tenant-a", "too-large", 2.0)
    assert (await enforcer.consult(rejected)).action == "block"
    await enforcer.record(rejected, 2.0)
    assert (await enforcer.consult(_request("tenant-a", "small", 0.1))).action == "allow"


@pytest.mark.asyncio
async def test_calls_in_one_turn_have_separate_holds_and_reconcile_independently():
    from dataclasses import replace
    repo = MemoryRepository()
    _tenant(repo, "tenant-a", cap=1.0)
    enforcer = TenantRepositoryBudgetEnforcer(repo)
    first = replace(_request("tenant-a", "same-turn", 0.6), call_id="call-1")
    second = replace(first, call_id="call-2")
    assert (await enforcer.consult(first)).action == "allow"
    await enforcer.record(first, 0.5)
    assert (await enforcer.consult(second)).action == "block"
    rows = repo.query_documents(LEDGER_COLLECTION)
    assert len(rows) == 2
    assert sum(r["chargedCostUsd"] for r in rows) == pytest.approx(0.5)

"""Real shared-repository accounting; never contacts an LLM."""
import os
from uuid import uuid4

import pytest

from budget.enforcer import BudgetConsultation
from budget.tenant_repository_enforcer import LEDGER_COLLECTION, TenantRepositoryBudgetEnforcer
from db.persistence import get_repository, reset_repository_for_testing
from db.tenants import TenantConfig, TenantDirectory


@pytest.mark.asyncio
async def test_postgres_budget_survives_recreation_and_isolates_tenants(monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL required")
    monkeypatch.setenv("DATA_BACKEND", "postgres")
    reset_repository_for_testing(None)
    repo = get_repository()
    tenants = [f"budget-ci-{uuid4().hex}" for _ in range(2)]
    try:
        for tid in tenants:
            TenantDirectory(repo).put(TenantConfig(
                tenantId=tid, displayName=tid, storageNamespace=tid,
                quota={"llmBudgetUsd": 1.0},
            ))
        def request(tid, call):
            return BudgetConsultation(tid, "budget-ci", "test-model", 0.6, "same-turn", call)
        first = request(tenants[0], "first")
        enforcer = TenantRepositoryBudgetEnforcer(repo)
        assert (await enforcer.consult(first)).action == "allow"
        await enforcer.record(first, 0.5)
        reset_repository_for_testing(None)
        repo = get_repository()
        recreated = TenantRepositoryBudgetEnforcer(repo)
        assert (await recreated.consult(request(tenants[0], "second"))).action == "block"
        assert (await recreated.consult(request(tenants[1], "second"))).action == "allow"
        a = repo.query_documents(LEDGER_COLLECTION, filters=[("tenantId", "==", tenants[0])])
        assert sum(row["chargedCostUsd"] for row in a) == pytest.approx(0.5)
    finally:
        for tid in tenants:
            for row in repo.query_documents(LEDGER_COLLECTION, filters=[("tenantId", "==", tid)]):
                repo.delete_document(LEDGER_COLLECTION, row["__id"])
            repo.delete_document("tenants", tid)
        reset_repository_for_testing(None)

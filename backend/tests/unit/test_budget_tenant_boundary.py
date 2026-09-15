"""Tenant-scoped budget boundary regression tests.

Issue #9 requires quota/budget enforcement to follow the explicit tenant
identity and to fail closed when a tenant-scoped quota cannot select a stable
bucket. Legacy budget configs keep their historical fail-open behaviour unless
they explicitly opt into ``missing_identity_policy: block``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from adk.budget_config import BudgetConfig
from auth.models import User
from budget.callback import make_budget_callbacks
from budget.enforcer import BudgetDecision, BudgetExceededError


class CapturingEnforcer:
    def __init__(self) -> None:
        self.consultations = []
        self.records = []

    async def consult(self, request):
        self.consultations.append(request)
        return BudgetDecision(
            action="allow",
            remaining_usd=10.0,
            period_end=None,
            message=None,
            retry_after_seconds=None,
        )

    async def record(self, request, actual_cost_usd):
        self.records.append((request, actual_cost_usd))


def _context(invocation_id: str = "inv-1"):
    return SimpleNamespace(invocation_id=invocation_id, state={})


def _request():
    return SimpleNamespace(
        model="gemini-2.5-flash",
        contents=[],
        config=SimpleNamespace(max_output_tokens=16),
    )


def test_budget_config_defaults_missing_identity_to_legacy_skip():
    cfg = BudgetConfig(identity_key="uid")
    assert cfg.missing_identity_policy == "skip"


def test_budget_config_accepts_fail_closed_missing_identity_policy():
    cfg = BudgetConfig(identity_key="tenant_id", missing_identity_policy="block")
    assert cfg.missing_identity_policy == "block"


def test_budget_config_rejects_unknown_missing_identity_policy():
    with pytest.raises(ValidationError):
        BudgetConfig(identity_key="tenant_id", missing_identity_policy="allow")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_tenant_scoped_budget_uses_explicit_tenant_id():
    enforcer = CapturingEnforcer()
    user = User(uid="same-user", email="member@example.com", tenant_id="tenant-a")
    cfg = BudgetConfig(identity_key="tenant_id", missing_identity_policy="block")

    before, _after = make_budget_callbacks(
        enforcer,
        user=user,
        skill_id="workspace-demo",
        budget_config=cfg,
    )
    await before(_context(), _request())

    assert len(enforcer.consultations) == 1
    assert enforcer.consultations[0].identity_value == "tenant-a"


@pytest.mark.asyncio
async def test_different_tenants_resolve_to_different_budget_buckets():
    enforcer = CapturingEnforcer()
    cfg = BudgetConfig(identity_key="tenant_id", missing_identity_policy="block")

    before_a, _ = make_budget_callbacks(
        enforcer,
        user=User(uid="shared-uid", tenant_id="tenant-a"),
        skill_id="workspace-demo",
        budget_config=cfg,
    )
    before_b, _ = make_budget_callbacks(
        enforcer,
        user=User(uid="shared-uid", tenant_id="tenant-b"),
        skill_id="workspace-demo",
        budget_config=cfg,
    )

    await before_a(_context("inv-a"), _request())
    await before_b(_context("inv-b"), _request())

    assert [c.identity_value for c in enforcer.consultations] == ["tenant-a", "tenant-b"]


@pytest.mark.asyncio
async def test_missing_tenant_id_blocks_before_enforcer_or_model_spend():
    enforcer = CapturingEnforcer()
    cfg = BudgetConfig(identity_key="tenant_id", missing_identity_policy="block")
    before, after = make_budget_callbacks(
        enforcer,
        user=User(uid="legacy-user", email="legacy@example.com", tenant_id=""),
        skill_id="workspace-demo",
        budget_config=cfg,
    )

    with pytest.raises(BudgetExceededError, match="tenant_id") as exc_info:
        await before(_context(), _request())

    assert exc_info.value.decision.action == "block"
    assert exc_info.value.decision.remaining_usd is None
    assert enforcer.consultations == []

    # A blocked call must never create a usage record either.
    await after(_context(), SimpleNamespace(usage_metadata=None))
    assert enforcer.records == []


@pytest.mark.asyncio
async def test_legacy_skip_policy_remains_backward_compatible():
    enforcer = CapturingEnforcer()
    cfg = BudgetConfig(identity_key="group_id")
    before, after = make_budget_callbacks(
        enforcer,
        user=User(uid="legacy-user", group_id=""),
        skill_id="legacy-skill",
        budget_config=cfg,
    )

    await before(_context(), _request())
    await after(_context(), SimpleNamespace(usage_metadata=None))

    assert enforcer.consultations == []
    assert enforcer.records == []

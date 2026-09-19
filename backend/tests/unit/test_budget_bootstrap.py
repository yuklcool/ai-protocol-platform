from __future__ import annotations

from unittest.mock import patch

import pytest

from budget.bootstrap import configure_budget_enforcer_from_env
from budget.enforcer import clear_registered_enforcer, get_registered_enforcer
from budget.tenant_repository_enforcer import TenantRepositoryBudgetEnforcer
from db.repositories.memory import MemoryRepository


@pytest.fixture(autouse=True)
def _reset_registry():
    clear_registered_enforcer()
    try:
        yield
    finally:
        clear_registered_enforcer()


def test_budget_bootstrap_is_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BUDGET_ENFORCER", raising=False)
    assert configure_budget_enforcer_from_env() == "off"
    assert get_registered_enforcer() is None


def test_budget_bootstrap_registers_tenant_repository_enforcer(monkeypatch) -> None:
    monkeypatch.setenv("BUDGET_ENFORCER", "tenant-repository")
    repo = MemoryRepository()
    with patch("budget.bootstrap.get_repository", return_value=repo):
        assert configure_budget_enforcer_from_env() == "tenant-repository"

    registered = get_registered_enforcer()
    assert isinstance(registered, TenantRepositoryBudgetEnforcer)
    assert registered.repository is repo


def test_budget_bootstrap_rejects_unknown_mode(monkeypatch) -> None:
    monkeypatch.setenv("BUDGET_ENFORCER", "mystery")
    with pytest.raises(RuntimeError, match="Unsupported BUDGET_ENFORCER"):
        configure_budget_enforcer_from_env()

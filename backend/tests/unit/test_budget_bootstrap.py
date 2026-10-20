from __future__ import annotations

import pytest

from budget.bootstrap import configure_budget_enforcer_from_env
from budget.enforcer import clear_registered_enforcer, get_registered_enforcer
from budget.in_memory_enforcer import InMemoryBudgetEnforcer


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


def test_budget_bootstrap_rejects_unknown_mode(monkeypatch) -> None:
    monkeypatch.setenv("BUDGET_ENFORCER", "mystery")
    with pytest.raises(RuntimeError, match="Unsupported BUDGET_ENFORCER"):
        configure_budget_enforcer_from_env()


def test_budget_bootstrap_registers_in_memory_enforcer(monkeypatch):
    monkeypatch.setenv("BUDGET_ENFORCER", "in-memory")
    assert configure_budget_enforcer_from_env() == "in-memory"
    assert isinstance(get_registered_enforcer(), InMemoryBudgetEnforcer)

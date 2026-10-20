"""Startup wiring for the pluggable budget enforcer."""

from __future__ import annotations

import logging
import os

from budget.enforcer import get_registered_enforcer, register_budget_enforcer
from budget.in_memory_enforcer import InMemoryBudgetEnforcer

log = logging.getLogger("budget")


def configure_budget_enforcer_from_env() -> str:
    raw = os.getenv("BUDGET_ENFORCER", "").strip().lower()
    if raw in {"", "off", "none", "disabled"}:
        return "off"

    if raw in {"in-memory", "memory"}:
        register_budget_enforcer(InMemoryBudgetEnforcer.from_env())
        log.info("budget.enforcer_registered mode=in-memory")
        return "in-memory"

    raise RuntimeError(f"Unsupported BUDGET_ENFORCER={raw!r}; expected off or in-memory")


__all__ = ["configure_budget_enforcer_from_env", "get_registered_enforcer"]

"""Startup wiring for the pluggable budget enforcer."""

from __future__ import annotations

import logging
import os

from budget.enforcer import get_registered_enforcer, register_budget_enforcer
from budget.in_memory_enforcer import InMemoryBudgetEnforcer
from budget.tenant_repository_enforcer import TenantRepositoryBudgetEnforcer
from db.persistence import get_repository

log = logging.getLogger("budget")


def configure_budget_enforcer_from_env() -> str:
    """Register the configured built-in enforcer and return its mode.

    Modes:
      - empty/off/none: no platform enforcer (historical default)
      - in-memory: reference single-process enforcer
      - tenant-repository: tenant quota + shared Repository/PostgreSQL ledger

    Explicit external registrations win when BUDGET_ENFORCER is disabled.
    """
    raw = os.getenv("BUDGET_ENFORCER", "").strip().lower()
    if raw in {"", "off", "none", "disabled"}:
        return "off"

    if raw in {"in-memory", "memory"}:
        register_budget_enforcer(InMemoryBudgetEnforcer.from_env())
        log.info("budget.enforcer_registered mode=in-memory")
        return "in-memory"

    if raw in {"tenant-repository", "tenant_repository", "repository"}:
        register_budget_enforcer(TenantRepositoryBudgetEnforcer(get_repository()))
        log.info("budget.enforcer_registered mode=tenant-repository")
        return "tenant-repository"

    raise RuntimeError(
        "Unsupported BUDGET_ENFORCER={!r}; expected off, in-memory, or tenant-repository".format(raw)
    )


__all__ = ["configure_budget_enforcer_from_env", "get_registered_enforcer"]

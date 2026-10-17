"""Preserve typed callback errors across the AG-UI adapter's background queue."""

from contextvars import ContextVar
from typing import Any

current_run_error: ContextVar[dict[str, Any] | None] = ContextVar("agui_run_error", default=None)


def record_run_error(*, code: str, message: str, **details: Any) -> None:
    slot = current_run_error.get()
    if slot is not None:
        slot.update(type="RUN_ERROR", code=code, message=message, **details)

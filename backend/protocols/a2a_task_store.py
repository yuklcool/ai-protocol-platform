"""Owner namespaces for the pinned A2A SDK's process-local task store."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import Task


class OwnerScopedTaskStore(TaskStore):
    """Keep identical task IDs independent across authenticated principals.

    The pinned SDK does not accept an owner_resolver on InMemoryTaskStore.
    Implement its public TaskStore contract instead of passing an unsupported
    constructor option (which prevents the entire A2A app from mounting).
    """

    def __init__(self, owner_resolver: Callable[[ServerCallContext | None], str]):
        self.owner_resolver = owner_resolver
        self._tasks: dict[tuple[str, str], Task] = {}
        self._lock = asyncio.Lock()

    async def save(self, task: Task, context: ServerCallContext | None = None) -> None:
        async with self._lock:
            self._tasks[self.owner_resolver(context), task.id] = task.model_copy(deep=True)

    async def get(self, task_id: str, context: ServerCallContext | None = None) -> Task | None:
        async with self._lock:
            task = self._tasks.get((self.owner_resolver(context), task_id))
            return task.model_copy(deep=True) if task else None

    async def delete(self, task_id: str, context: ServerCallContext | None = None) -> None:
        async with self._lock:
            self._tasks.pop((self.owner_resolver(context), task_id), None)

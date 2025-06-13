from __future__ import annotations

"""Asynchronous engine for running backfill jobs."""

import asyncio

from .backfill import BackfillSource
from .node import Node


class BackfillEngine:
    """Run backfill jobs concurrently using ``asyncio`` tasks."""

    def __init__(self, source: BackfillSource, *, max_retries: int = 3) -> None:
        self.source = source
        self.max_retries = max_retries
        self._tasks: set[asyncio.Task] = set()

    # --------------------------------------------------------------
    async def _run_job(self, node: Node, start: int, end: int) -> None:
        attempts = 0
        while True:
            try:
                df = await asyncio.to_thread(
                    self.source.fetch,
                    start,
                    end,
                    node_id=node.node_id,
                    interval=node.interval,
                )
                if df is None:
                    return
                items = [
                    (int(row.get("ts", 0)), row.to_dict())
                    for _, row in df.iterrows()
                ]
                node.cache.backfill_bulk(node.node_id, node.interval, items)
                return
            except Exception:
                attempts += 1
                if attempts > self.max_retries:
                    raise
                await asyncio.sleep(0.1 * attempts)

    # --------------------------------------------------------------
    def submit(self, node: Node, start: int, end: int) -> asyncio.Task:
        """Schedule a backfill job and return the created task."""
        task = asyncio.create_task(self._run_job(node, start, end))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def wait(self) -> None:
        """Wait for all scheduled backfill jobs to finish."""
        if self._tasks:
            await asyncio.gather(*self._tasks)

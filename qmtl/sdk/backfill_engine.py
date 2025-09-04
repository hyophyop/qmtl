from __future__ import annotations

"""Asynchronous engine for running backfill jobs."""

import asyncio
import logging

from qmtl.io import HistoryProvider
from .node import Node
from . import metrics as sdk_metrics

logger = logging.getLogger(__name__)


class BackfillEngine:
    """Run backfill jobs concurrently using ``asyncio`` tasks."""

    def __init__(self, source: HistoryProvider, *, max_retries: int = 3) -> None:
        self.source = source
        self.max_retries = max_retries
        self._tasks: set[asyncio.Task] = set()

    # --------------------------------------------------------------
    async def _run_job(self, node: Node, start: int, end: int) -> None:
        sdk_metrics.observe_backfill_start(node.node_id, node.interval)
        logger.info(
            "backfill.start",
            extra={
                "node_id": node.node_id,
                "interval": node.interval,
                "start": start,
                "end": end,
            },
        )

        attempts = 0
        while True:
            try:
                df = await self.source.fetch(
                    start,
                    end,
                    node_id=node.node_id,
                    interval=node.interval,
                )
                if df is None:
                    sdk_metrics.observe_backfill_complete(node.node_id, node.interval, end)
                    logger.info(
                        "backfill.complete",
                        extra={
                            "node_id": node.node_id,
                            "interval": node.interval,
                            "start": start,
                            "end": end,
                        },
                    )
                    return
                items = [
                    (int(row.get("ts", 0)), row.to_dict())
                    for _, row in df.iterrows()
                ]
                node.cache.backfill_bulk(node.node_id, node.interval, items)
                sdk_metrics.observe_backfill_complete(node.node_id, node.interval, end)
                logger.info(
                    "backfill.complete",
                    extra={
                        "node_id": node.node_id,
                        "interval": node.interval,
                        "start": start,
                        "end": end,
                    },
                )
                return
            except Exception:
                attempts += 1
                sdk_metrics.observe_backfill_retry(node.node_id, node.interval)
                logger.info(
                    "backfill.retry",
                    extra={
                        "node_id": node.node_id,
                        "interval": node.interval,
                        "attempt": attempts,
                    },
                )
                if attempts > self.max_retries:
                    sdk_metrics.observe_backfill_failure(node.node_id, node.interval)
                    logger.error(
                        "backfill.failed",
                        extra={
                            "node_id": node.node_id,
                            "interval": node.interval,
                            "attempts": attempts,
                        },
                    )
                    raise
                await self.poll_source_ready()

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

    async def poll_source_ready(self) -> None:
        """Poll the source for readiness before retrying."""
        if hasattr(self.source, "ready"):
            while True:
                try:
                    if await self.source.ready():
                        return
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0)

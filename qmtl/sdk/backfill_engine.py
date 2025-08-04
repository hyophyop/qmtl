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

    def __init__(self, source: HistoryProvider) -> None:
        self.source = source
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
        except Exception:
            # Caller is responsible for retrying and recording failure metrics.
            raise

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

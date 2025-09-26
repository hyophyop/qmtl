from __future__ import annotations

"""Asynchronous engine for running backfill jobs."""

import asyncio
import logging

from qmtl.runtime.io import HistoryProvider
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
                metadata = getattr(self.source, "last_fetch_metadata", None)
                if df is None:
                    await self._process_metadata(node, metadata)
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
                await self._process_metadata(node, metadata)
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

    async def _process_metadata(self, node: Node, metadata) -> None:
        if metadata is None:
            return
        try:
            node.last_fetch_metadata = metadata
        except Exception:
            pass

        try:
            coverage = metadata.coverage_bounds
            if coverage is not None:
                setattr(node, "last_coverage_bounds", coverage)
        except Exception:
            pass

        artifact = getattr(metadata, "artifact", None)
        try:
            if artifact is not None:
                node.update_compute_context(
                    as_of=getattr(artifact, "as_of", None),
                    dataset_fingerprint=getattr(artifact, "dataset_fingerprint", None),
                )
            elif getattr(metadata, "as_of", None) is not None:
                node.update_compute_context(as_of=metadata.as_of)
        except Exception:
            logger.debug("failed to update node compute context from metadata", exc_info=True)

        try:
            setattr(node, "seamless_conformance_flags", dict(metadata.conformance_flags))
        except Exception:
            pass
        try:
            setattr(
                node,
                "seamless_conformance_warnings",
                list(metadata.conformance_warnings or ()),
            )
        except Exception:
            pass

        await self._publish_metadata(node, metadata)

    async def _publish_metadata(self, node: Node, metadata) -> None:
        gateway_url = getattr(node, "gateway_url", None)
        strategy_id = getattr(node, "strategy_id", None)
        if not gateway_url or not strategy_id:
            return

        try:
            from .runner import Runner

            services = Runner.services()
            client = getattr(services, "gateway_client", None)
            if client is None:
                return
        except Exception:
            logger.debug("gateway client unavailable for metadata publish", exc_info=True)
            return

        artifact = getattr(metadata, "artifact", None)
        dataset_fp = getattr(metadata, "dataset_fingerprint", None)
        if dataset_fp is None and artifact is not None:
            dataset_fp = getattr(artifact, "dataset_fingerprint", None)
        if dataset_fp is None:
            dataset_fp = node.dataset_fingerprint

        as_of_value = getattr(metadata, "as_of", None)
        if as_of_value is None and artifact is not None:
            as_of_value = getattr(artifact, "as_of", None)
        if as_of_value is None:
            as_of_value = getattr(node.compute_context, "as_of", None)

        payload = {
            "node_id": node.node_id,
            "interval": int(getattr(node, "interval", 0) or 0),
            "rows": getattr(metadata, "rows", 0),
            "coverage_bounds": list(metadata.coverage_bounds) if metadata.coverage_bounds else None,
            "conformance_flags": metadata.conformance_flags or {},
            "conformance_warnings": list(metadata.conformance_warnings or ()),
            "dataset_fingerprint": dataset_fp,
            "as_of": as_of_value,
            "world_id": getattr(node, "world_id", None),
            "execution_domain": getattr(node, "execution_domain", None),
        }
        if artifact is not None:
            payload["artifact"] = {
                "dataset_fingerprint": getattr(artifact, "dataset_fingerprint", None),
                "as_of": getattr(artifact, "as_of", None),
                "rows": getattr(artifact, "rows", 0),
                "uri": getattr(artifact, "uri", None),
            }

        try:
            await client.post_history_metadata(
                gateway_url=gateway_url,
                strategy_id=strategy_id,
                payload=payload,
            )
        except Exception:
            logger.debug("failed to publish seamless metadata", exc_info=True)

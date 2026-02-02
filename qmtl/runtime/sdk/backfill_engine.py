from __future__ import annotations

"""Asynchronous engine for running backfill jobs."""

import asyncio
import logging
from typing import Any, cast

import polars as pl

from qmtl.runtime.sdk.data_io import HistoryProvider
from . import metrics as sdk_metrics

logger = logging.getLogger(__name__)


class BackfillEngine:
    """Run backfill jobs concurrently using ``asyncio`` tasks."""

    def __init__(
        self,
        source: HistoryProvider,
        *,
        max_retries: int = 3,
        gateway_client: Any | None = None,
    ) -> None:
        self.source = source
        self.max_retries = max_retries
        self._tasks: set[asyncio.Task] = set()
        self._gateway_client = gateway_client

    # --------------------------------------------------------------
    async def _run_job(self, node: Any, start: int, end: int) -> None:
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
                df = cast(
                    pl.DataFrame | None,
                    await self.source.fetch(
                        start,
                        end,
                        node_id=node.node_id,
                        interval=node.interval,
                    ),
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
                items = []
                for row in df.iter_rows(named=True):
                    items.append((int(row.get("ts", 0)), dict(row)))
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
    def submit(self, node: Any, start: int, end: int) -> asyncio.Task:
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

    async def _process_metadata(self, node: Any, metadata) -> None:
        if metadata is None:
            return
        self._set_last_fetch_metadata(node, metadata)
        self._apply_coverage_bounds(node, metadata)
        self._update_compute_context_from_metadata(node, metadata)
        self._apply_conformance_flags(node, metadata)
        self._apply_conformance_warnings(node, metadata)

        await self._publish_metadata(node, metadata)

    @staticmethod
    def _set_last_fetch_metadata(node: Any, metadata) -> None:
        try:
            node.last_fetch_metadata = metadata
        except Exception:
            pass

    @staticmethod
    def _apply_coverage_bounds(node: Any, metadata) -> None:
        try:
            coverage = getattr(metadata, "coverage_bounds", None)
            if coverage is not None:
                setattr(node, "last_coverage_bounds", coverage)
        except Exception:
            pass

    @staticmethod
    def _update_compute_context_from_metadata(node: Any, metadata) -> None:
        artifact = getattr(metadata, "artifact", None)
        try:
            if artifact is not None:
                node.update_compute_context(
                    as_of=getattr(artifact, "as_of", None),
                    dataset_fingerprint=getattr(artifact, "dataset_fingerprint", None),
                )
                return

            as_of = getattr(metadata, "as_of", None)
            if as_of is not None:
                node.update_compute_context(as_of=as_of)
        except Exception:
            logger.debug("failed to update node compute context from metadata", exc_info=True)

    @staticmethod
    def _apply_conformance_flags(node: Any, metadata) -> None:
        try:
            flags = getattr(metadata, "conformance_flags", None)
            if flags is not None:
                setattr(node, "seamless_conformance_flags", dict(flags))
        except Exception:
            pass

    @staticmethod
    def _apply_conformance_warnings(node: Any, metadata) -> None:
        try:
            warnings = getattr(metadata, "conformance_warnings", None) or ()
            setattr(node, "seamless_conformance_warnings", list(warnings))
        except Exception:
            pass

    async def _publish_metadata(self, node: Any, metadata) -> None:
        gateway_url = getattr(node, "gateway_url", None)
        strategy_id = getattr(node, "strategy_id", None)
        if not gateway_url or not strategy_id:
            return

        client = self._resolve_gateway_client()
        if client is None:
            return

        artifact = getattr(metadata, "artifact", None)
        dataset_fp = self._resolve_dataset_fingerprint(metadata, artifact, node)
        as_of_value = self._resolve_as_of(metadata, artifact, node)
        payload = self._build_metadata_payload(
            node=node,
            metadata=metadata,
            dataset_fp=dataset_fp,
            as_of_value=as_of_value,
            artifact=artifact,
        )

        try:
            await client.post_history_metadata(
                gateway_url=gateway_url,
                strategy_id=strategy_id,
                payload=payload,
            )
        except Exception:
            logger.debug("failed to publish seamless metadata", exc_info=True)

    def _resolve_gateway_client(self):
        if self._gateway_client is not None:
            return self._gateway_client
        try:
            import importlib

            runner_mod = importlib.import_module("qmtl.runtime.sdk.runner")
            Runner = getattr(runner_mod, "Runner")
            return getattr(Runner.services(), "gateway_client", None)
        except Exception:
            logger.debug("gateway client unavailable for metadata publish", exc_info=True)
            return None

    def _resolve_dataset_fingerprint(self, metadata, artifact, node: Any):
        dataset_fp = getattr(metadata, "dataset_fingerprint", None)
        if dataset_fp is None and artifact is not None:
            dataset_fp = getattr(artifact, "dataset_fingerprint", None)
        if dataset_fp is None:
            dataset_fp = node.dataset_fingerprint
        return dataset_fp

    def _resolve_as_of(self, metadata, artifact, node: Any):
        as_of_value = getattr(metadata, "as_of", None)
        if as_of_value is None and artifact is not None:
            as_of_value = getattr(artifact, "as_of", None)
        if as_of_value is None:
            as_of_value = getattr(node.compute_context, "as_of", None)
        return as_of_value

    def _build_metadata_payload(
        self,
        *,
        node: Any,
        metadata,
        dataset_fp,
        as_of_value,
        artifact,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
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
        return payload

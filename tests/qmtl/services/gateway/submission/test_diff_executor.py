from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from qmtl.services.gateway.submission.diff_executor import (
    DiffExecutor,
    DiffOutcome,
)


class _ComputeContext:
    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs

    def diff_kwargs(self) -> dict[str, Any]:
        return dict(self._kwargs)


class _Chunk:
    def __init__(
        self,
        *,
        sentinel_id: str | None,
        queue_map: dict[str, str] | None,
        crc32: int | None,
    ) -> None:
        self.sentinel_id = sentinel_id
        self.queue_map = queue_map or {}
        self.crc32 = crc32

    def HasField(self, field: str) -> bool:  # pragma: no cover - API shim
        return getattr(self, field, None) is not None


@pytest.mark.asyncio
async def test_queue_map_strategy_aggregates_unique_bindings() -> None:
    dagmanager = AsyncMock()
    ctx = _ComputeContext(foo="bar")

    chunk_primary = _Chunk(
        sentinel_id="sent-1",
        queue_map={"nodeA:sub#1": "queue-A", "nodeA:sub#2": "queue-A"},
        crc32=1234,
    )
    chunk_secondary = _Chunk(
        sentinel_id=None,
        queue_map={"nodeB#0": "queue-B"},
        crc32=1234,
    )

    async def diff_side_effect(strategy_id, dag_json, *, world_id, **kwargs):
        assert kwargs == {"foo": "bar"}
        if world_id == "w1":
            return chunk_primary
        if world_id == "w2":
            return chunk_secondary
        return None

    dagmanager.diff.side_effect = diff_side_effect

    executor = DiffExecutor(dagmanager)
    outcome = await executor.run(
        strategy_id="strat",
        dag_json='{"schema_version": "v1", "nodes": []}',
        worlds=["w1", "w2"],
        fallback_world_id=None,
        compute_ctx=ctx,
        timeout=1.0,
        prefer_queue_map=True,
        expected_crc32=1234,
    )

    assert outcome == DiffOutcome(
        sentinel_id="sent-1",
        queue_map={
            "nodeA": [{"queue": "queue-A", "global": False}],
            "nodeB": [{"queue": "queue-B", "global": False}],
        },
    )


@pytest.mark.asyncio
async def test_single_world_strategy_returns_sentinel_and_queue_map() -> None:
    dagmanager = AsyncMock()
    ctx = _ComputeContext()

    dagmanager.diff.return_value = _Chunk(
        sentinel_id="sent-2",
        queue_map={"nodeC#0": "queue-C"},
        crc32=555,
    )

    executor = DiffExecutor(dagmanager)
    outcome = await executor.run(
        strategy_id="strat",
        dag_json='{"schema_version": "v1", "nodes": []}',
        worlds=["w1"],
        fallback_world_id="fallback",
        compute_ctx=ctx,
        timeout=1.0,
        prefer_queue_map=True,
        expected_crc32=555,
    )

    assert outcome == DiffOutcome(
        sentinel_id="sent-2",
        queue_map={"nodeC": [{"queue": "queue-C", "global": False}]},
    )

    dagmanager.diff.assert_awaited_once()
    _args, kwargs = dagmanager.diff.await_args
    assert kwargs["world_id"] == "w1"


@pytest.mark.asyncio
async def test_raises_on_crc_mismatch() -> None:
    dagmanager = AsyncMock()
    ctx = _ComputeContext()
    dagmanager.diff.return_value = _Chunk(
        sentinel_id="sent-3",
        queue_map={},
        crc32=1,
    )

    executor = DiffExecutor(dagmanager)
    with pytest.raises(ValueError, match="CRC32 mismatch"):
        await executor.run(
            strategy_id="strat",
            dag_json='{"schema_version": "v1", "nodes": []}',
            worlds=["w1"],
            fallback_world_id=None,
            compute_ctx=ctx,
            timeout=1.0,
            prefer_queue_map=False,
            expected_crc32=2,
        )

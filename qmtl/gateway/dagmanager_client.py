from __future__ import annotations

import asyncio
from typing import Dict

import grpc

from ..proto import dagmanager_pb2, dagmanager_pb2_grpc
from ..common import AsyncCircuitBreaker
from . import metrics as gw_metrics


class DagManagerClient:
    """gRPC client for DAG‑Manager services using a persistent channel."""

    def __init__(self, target: str, *, breaker_max_failures: int = 3) -> None:
        self._target = target
        self._created_loop = None
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._created_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._created_loop)
        self._channel = grpc.aio.insecure_channel(self._target)
        self._health_stub = dagmanager_pb2_grpc.HealthCheckStub(self._channel)
        self._diff_stub = dagmanager_pb2_grpc.DiffServiceStub(self._channel)
        self._tag_stub = dagmanager_pb2_grpc.TagQueryStub(self._channel)
        self._breaker = AsyncCircuitBreaker(
            max_failures=breaker_max_failures,
            on_open=lambda: (
                gw_metrics.dagclient_breaker_state.set(1),
                gw_metrics.dagclient_breaker_open_total.inc(),
            ),
            on_close=lambda: (
                gw_metrics.dagclient_breaker_state.set(0),
                gw_metrics.dagclient_breaker_failures.set(0),
            ),
            on_failure=lambda c: gw_metrics.dagclient_breaker_failures.set(c),
        )
        gw_metrics.dagclient_breaker_state.set(0)
        gw_metrics.dagclient_breaker_failures.set(0)

    async def close(self) -> None:
        """Close the underlying gRPC channel."""
        await self._channel.close()
        if self._created_loop is not None:
            self._created_loop.close()

    @property
    def breaker(self) -> AsyncCircuitBreaker:
        """Return the circuit breaker instance."""
        return self._breaker

    async def status(self) -> bool:
        """Return ``True`` if the remote DAG manager reports healthy status."""
        @self._breaker
        async def _call() -> bool:
            reply = await self._health_stub.Status(dagmanager_pb2.StatusRequest())
            return reply.neo4j == "ok" and reply.state == "running"

        try:
            result = await _call()
            if result:
                self._breaker.reset()
            gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
            return result
        except Exception:
            return False

    async def diff(self, strategy_id: str, dag_json: str) -> dagmanager_pb2.DiffChunk:
        """Call ``DiffService.Diff`` with retries and collect the stream."""
        request = dagmanager_pb2.DiffRequest(strategy_id=strategy_id, dag_json=dag_json)

        @self._breaker
        async def _call() -> dagmanager_pb2.DiffChunk:
            backoff = 0.5
            retries = 5
            for attempt in range(retries):
                try:
                    queue_map: Dict[str, str] = {}
                    sentinel_id = ""
                    buffer_nodes: list[dagmanager_pb2.BufferInstruction] = []
                    async for chunk in self._diff_stub.Diff(request):
                        queue_map.update(dict(chunk.queue_map))
                        sentinel_id = chunk.sentinel_id
                        buffer_nodes.extend(chunk.buffer_nodes)
                    return dagmanager_pb2.DiffChunk(
                        queue_map=queue_map,
                        sentinel_id=sentinel_id,
                        buffer_nodes=buffer_nodes,
                    )
                except Exception:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 4)
            raise RuntimeError("unreachable")

        result = await _call()
        gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
        return result

    async def get_queues_by_tag(
        self, tags: list[str], interval: int, match_mode: str = "any"
    ) -> list[str]:
        """Return queues matching ``tags`` and ``interval``.

        Parameters
        ----------
        tags:
            태그 이름 목록.
        interval:
            조회할 바 주기(초 단위).
        match_mode:
            ``"any"`` (기본값)일 때는 하나 이상의 태그가 일치하면 매칭하며,
            ``"all"`` 은 모든 태그가 존재하는 큐만 반환한다.

        This delegates to DAG‑Manager which is expected to expose a
        ``TagQuery`` RPC. Retries with exponential backoff are applied
        similar to :meth:`diff`.
        """
        request = dagmanager_pb2.TagQueryRequest(
            tags=tags, interval=interval, match_mode=match_mode
        )
        
        @self._breaker
        async def _call() -> list[str]:
            backoff = 0.5
            retries = 5
            for attempt in range(retries):
                try:
                    response = await self._tag_stub.GetQueues(request)
                    return list(response.queues)
                except Exception:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 4)
            return []

        result = await _call()
        gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
        return result


__all__ = ["DagManagerClient"]

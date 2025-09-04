from __future__ import annotations

import asyncio
from typing import Dict

import grpc

from opentelemetry.instrumentation.grpc import aio_client_interceptors

from ..proto import dagmanager_pb2, dagmanager_pb2_grpc
from ..common import AsyncCircuitBreaker
from . import metrics as gw_metrics


class DagManagerClient:
    """gRPC client for DAG Manager services using a persistent channel."""

    def __init__(self, target: str, *, breaker_max_failures: int = 3) -> None:
        self._target = target
        # Do not create or set a global event loop here; the ASGI runtime
        # guarantees a running loop when RPCs are awaited. Creating a loop
        # at import time leaks resources under pytest's unraisable warnings.
        self._created_loop = None
        # Lazily create channel/stubs on first use to avoid touching the
        # event loop at import time (prevents resource warnings under pytest).
        self._channel = None
        self._health_stub = None
        self._diff_stub = None
        self._tag_stub = None
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

    def _ensure_channel(self) -> None:
        if self._channel is None:
            try:
                self._channel = grpc.aio.insecure_channel(
                    self._target, interceptors=aio_client_interceptors()
                )
            except TypeError:
                self._channel = grpc.aio.insecure_channel(self._target)
            self._health_stub = dagmanager_pb2_grpc.HealthCheckStub(self._channel)
            self._diff_stub = dagmanager_pb2_grpc.DiffServiceStub(self._channel)
            self._tag_stub = dagmanager_pb2_grpc.TagQueryStub(self._channel)

    async def _wait_for_service(self, timeout: float = 5.0) -> None:
        """Poll the DAG Manager health endpoint until it reports ready.

        Raises
        ------
        RuntimeError
            If the service does not report healthy within ``timeout`` seconds.
        """
        self._ensure_channel()
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                reply = await self._health_stub.Status(
                    dagmanager_pb2.StatusRequest()
                )
                if reply.neo4j == "ok" and reply.state == "running":
                    return
            except Exception:
                pass
            if asyncio.get_running_loop().time() > deadline:
                raise RuntimeError("DAG Manager unavailable")
            await asyncio.sleep(0.5)

    async def close(self) -> None:
        """Close the underlying gRPC channel."""
        if self._channel is not None:
            await self._channel.close()
        if self._created_loop is not None:
            self._created_loop.close()

    @property
    def breaker(self) -> AsyncCircuitBreaker:
        """Return the circuit breaker instance."""
        return self._breaker

    async def status(self) -> bool:
        """Return ``True`` if the remote DAG Manager reports healthy status."""
        @self._breaker
        async def _call() -> bool:
            self._ensure_channel()
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

    async def diff(
        self, strategy_id: str, dag_json: str, *, world_id: str | None = None
    ) -> dagmanager_pb2.DiffChunk | None:
        """Call ``DiffService.Diff`` with retries and collect the stream.

        Returns ``None`` when the request ultimately fails or the circuit is
        open."""
        request = dagmanager_pb2.DiffRequest(strategy_id=strategy_id, dag_json=dag_json)

        @self._breaker
        async def _call() -> dagmanager_pb2.DiffChunk:
            self._ensure_channel()
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
                        await self._diff_stub.AckChunk(
                            dagmanager_pb2.ChunkAck(
                                sentinel_id=chunk.sentinel_id, chunk_id=0
                            )
                        )
                    return dagmanager_pb2.DiffChunk(
                        queue_map=queue_map,
                        sentinel_id=sentinel_id,
                        buffer_nodes=buffer_nodes,
                    )
                except Exception:
                    if attempt == retries - 1:
                        raise
                    await self._wait_for_service()
            raise RuntimeError("unreachable")

        try:
            result = await _call()
        except Exception:
            gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
            return None
        else:
            self._breaker.reset()
            gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
            if result and world_id:
                result.queue_map.update(
                    {k: f"w/{world_id}/{v}" for k, v in result.queue_map.items()}
                )
            return result

    async def get_queues_by_tag(
        self,
        tags: list[str],
        interval: int,
        match_mode: str = "any",
        world_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return queue descriptors matching ``tags`` and ``interval``.

        Parameters
        ----------
        tags:
            태그 이름 목록.
        interval:
            조회할 바 주기(초 단위).
        match_mode:
            ``"any"`` (기본값)일 때는 하나 이상의 태그가 일치하면 매칭하며,
            ``"all"`` 은 모든 태그가 존재하는 큐만 반환한다.

        This delegates to DAG Manager which is expected to expose a
        ``TagQuery`` RPC. Retries poll the service health between attempts
        similar to :meth:`diff`.
        """
        request = dagmanager_pb2.TagQueryRequest(
            tags=tags, interval=interval, match_mode=match_mode
        )

        @self._breaker
        async def _call() -> list[dict[str, object]]:
            self._ensure_channel()
            retries = 5
            for attempt in range(retries):
                try:
                    response = await self._tag_stub.GetQueues(request)
                    return [
                        {
                            "queue": f"w/{world_id}/{q.queue}" if world_id else q.queue,
                            "global": getattr(q, "global"),
                        }
                        for q in response.queues
                    ]
                except Exception:
                    if attempt == retries - 1:
                        raise
                    await self._wait_for_service()
            return []

        try:
            result = await _call()
        except Exception:
            gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
            return []
        else:
            self._breaker.reset()
            gw_metrics.dagclient_breaker_failures.set(self._breaker.failures)
            return result


__all__ = ["DagManagerClient"]

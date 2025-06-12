from __future__ import annotations

import asyncio
from typing import Dict

import grpc

from ..proto import dagmanager_pb2, dagmanager_pb2_grpc


class DagManagerClient:
    """gRPC client for DAG‑Manager services."""

    def __init__(self, target: str) -> None:
        self._target = target

    async def diff(self, strategy_id: str, dag_json: str) -> dagmanager_pb2.DiffChunk:
        """Call ``DiffService.Diff`` with retries and collect the stream."""
        request = dagmanager_pb2.DiffRequest(strategy_id=strategy_id, dag_json=dag_json)
        backoff = 0.5
        retries = 5
        for attempt in range(retries):
            channel = grpc.aio.insecure_channel(self._target)
            stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
            try:
                queue_map: Dict[str, str] = {}
                sentinel_id = ""
                buffer_nodes: list[str] = []
                async for chunk in stub.Diff(request):
                    queue_map.update(dict(chunk.queue_map))
                    sentinel_id = chunk.sentinel_id
                    buffer_nodes.extend(chunk.buffer_nodes)
                return dagmanager_pb2.DiffChunk(
                    queue_map=queue_map, sentinel_id=sentinel_id, buffer_nodes=buffer_nodes
                )
            except Exception:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 4)
            finally:
                await channel.close()

    async def get_queues_by_tag(self, tags: list[str], interval: int) -> list[str]:
        """Return queues matching ``tags`` and ``interval``.

        This delegates to DAG‑Manager which is expected to expose a
        ``TagQuery`` RPC. Retries with exponential backoff are applied
        similar to :meth:`diff`.
        """
        request = dagmanager_pb2.TagQueryRequest(tags=tags, interval=interval)
        backoff = 0.5
        retries = 5
        for attempt in range(retries):
            channel = grpc.aio.insecure_channel(self._target)
            stub = dagmanager_pb2_grpc.TagQueryStub(channel)
            try:
                response = await stub.GetQueues(request)
                return list(response.queues)
            except Exception:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 4)
            finally:
                await channel.close()
        return []


__all__ = ["DagManagerClient"]

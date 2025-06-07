from __future__ import annotations

from typing import AsyncIterable

import grpc

from .diff_service import DiffService, DiffRequest
from .callbacks import post_with_backoff
from .gc import GarbageCollector
from ..proto import dagmanager_pb2, dagmanager_pb2_grpc


class DiffServiceServicer(dagmanager_pb2_grpc.DiffServiceServicer):
    def __init__(self, service: DiffService, callback_url: str | None = None) -> None:
        self._service = service
        self._callback_url = callback_url

    async def Diff(
        self,
        request: dagmanager_pb2.DiffRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterable[dagmanager_pb2.DiffChunk]:
        chunk = self._service.diff(
            DiffRequest(strategy_id=request.strategy_id, dag_json=request.dag_json)
        )
        pb = dagmanager_pb2.DiffChunk(queue_map=chunk.queue_map, sentinel_id=chunk.sentinel_id)
        if self._callback_url:
            # Consider submitting this to a background task
            # if the callback should not block the stream or terminate it on failure.
            await post_with_backoff(
                self._callback_url,
                {"event": "diff", "strategy_id": request.strategy_id},
            )
        yield pb


class AdminServiceServicer(dagmanager_pb2_grpc.AdminServiceServicer):
    def __init__(self, gc: GarbageCollector | None = None) -> None:
        self._gc = gc

    async def Cleanup(
        self,
        request: dagmanager_pb2.CleanupRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.CleanupResponse:
        if self._gc is not None:
            self._gc.collect()
        return dagmanager_pb2.CleanupResponse()

    async def GetQueueStats(
        self,
        request: dagmanager_pb2.QueueStatsRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.QueueStats:
        return dagmanager_pb2.QueueStats()


class HealthServicer(dagmanager_pb2_grpc.HealthCheckServicer):
    async def Ping(
        self,
        request: dagmanager_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.PingReply:
        return dagmanager_pb2.PingReply()


def serve(
    diff_service: DiffService,
    *,
    host: str = "0.0.0.0",
    port: int = 50051,
    callback_url: str | None = None,
    gc: GarbageCollector | None = None,
) -> tuple[grpc.aio.Server, int]:
    server = grpc.aio.server()
    dagmanager_pb2_grpc.add_DiffServiceServicer_to_server(
        DiffServiceServicer(diff_service, callback_url), server
    )
    dagmanager_pb2_grpc.add_AdminServiceServicer_to_server(AdminServiceServicer(gc), server)
    dagmanager_pb2_grpc.add_HealthCheckServicer_to_server(HealthServicer(), server)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    return server, bound_port

from __future__ import annotations

from typing import AsyncIterable, Dict
import asyncio
import threading

import grpc

from .diff_service import (
    DiffService,
    DiffRequest,
    Neo4jNodeRepository,
    KafkaQueueManager,
    StreamSender,
    DiffChunk,
)
from .kafka_admin import KafkaAdmin
from .callbacks import post_with_backoff
from ..common.cloudevents import format_event
from .gc import GarbageCollector
from ..proto import dagmanager_pb2, dagmanager_pb2_grpc
from .status import get_status


class _GrpcStream(StreamSender):
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[DiffChunk] = asyncio.Queue()
        self._ack = threading.Event()

    def send(self, chunk: DiffChunk) -> None:
        asyncio.run_coroutine_threadsafe(self.queue.put(chunk), self.loop)

    def wait_for_ack(self) -> None:
        self._ack.wait()
        self._ack.clear()

    def ack(self) -> None:
        self._ack.set()


class DiffServiceServicer(dagmanager_pb2_grpc.DiffServiceServicer):
    def __init__(self, service: DiffService, callback_url: str | None = None) -> None:
        self._service = service
        self._callback_url = callback_url

    def __init__(self, service: DiffService, callback_url: str | None = None) -> None:
        self._service = service
        self._callback_url = callback_url
        self._streams: Dict[str, _GrpcStream] = {}

    async def Diff(
        self,
        request: dagmanager_pb2.DiffRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterable[dagmanager_pb2.DiffChunk]:
        sentinel_id = f"{request.strategy_id}-sentinel"
        stream = _GrpcStream(asyncio.get_running_loop())
        self._streams[sentinel_id] = stream
        svc = DiffService(self._service.node_repo, self._service.queue_manager, stream)
        loop = asyncio.get_running_loop()

        def run_diff() -> DiffChunk:
            return svc.diff(DiffRequest(strategy_id=request.strategy_id, dag_json=request.dag_json))

        fut = loop.run_in_executor(None, run_diff)
        try:
            while True:
                if fut.done() and stream.queue.empty():
                    break
                try:
                    chunk = await asyncio.wait_for(stream.queue.get(), 0.1)
                except asyncio.TimeoutError:
                    continue
                pb = dagmanager_pb2.DiffChunk(
                    queue_map=chunk.queue_map,
                    sentinel_id=chunk.sentinel_id,
                    buffer_nodes=[
                        dagmanager_pb2.BufferInstruction(
                            node_id=n.node_id,
                            node_type=n.node_type,
                            code_hash=n.code_hash,
                            schema_hash=n.schema_hash,
                            interval=n.interval or 0,
                            period=n.period or 0,
                            tags=list(n.tags),
                            lag=n.lag,
                        )
                        for n in getattr(chunk, 'buffering_nodes', [])
                    ],
                )
                if self._callback_url and getattr(chunk, 'new_nodes', None):
                    for node in chunk.new_nodes:
                        if node.tags and node.interval is not None:
                            event = format_event(
                                "qmtl.dagmanager",
                                "queue_update",
                                {
                                    "tags": node.tags,
                                    "interval": node.interval,
                                    "queues": [chunk.queue_map.get(node.node_id, "")],
                                },
                            )
                            await post_with_backoff(self._callback_url, event)
                yield pb
        finally:
            fut.cancel()
            await fut
            self._streams.pop(sentinel_id, None)

    async def AckChunk(
        self,
        request: dagmanager_pb2.ChunkAck,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.ChunkAck:
        stream = self._streams.get(request.sentinel_id)
        if stream is not None:
            stream.ack()
        return dagmanager_pb2.ChunkAck(
            sentinel_id=request.sentinel_id, chunk_id=request.chunk_id
        )


class AdminServiceServicer(dagmanager_pb2_grpc.AdminServiceServicer):
    def __init__(
        self,
        gc: GarbageCollector | None = None,
        admin: KafkaAdmin | None = None,
        repo: Neo4jNodeRepository | None = None,
        diff: DiffService | None = None,
        callback_url: str | None = None,
    ) -> None:
        self._gc = gc
        self._admin = admin
        self._repo = repo
        self._diff = diff
        self._callback_url = callback_url

    async def Cleanup(
        self,
        request: dagmanager_pb2.CleanupRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.CleanupResponse:
        if self._gc is not None:
            processed = self._gc.collect()
            if self._callback_url:
                for qi in processed:
                    if getattr(qi, "interval", None) is not None:
                        event = format_event(
                            "qmtl.dagmanager",
                            "queue_update",
                            {
                                "tags": [qi.tag],
                                "interval": qi.interval,
                                "queues": [qi.name],
                            },
                        )
                        await post_with_backoff(self._callback_url, event)
        return dagmanager_pb2.CleanupResponse()

    async def GetQueueStats(
        self,
        request: dagmanager_pb2.QueueStatsRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.QueueStats:
        sizes = {}
        if self._admin is not None:
            sizes = self._admin.get_topic_sizes()
        if request.filter and self._repo is not None and sizes:
            tags: list[str] = []
            interval = 0
            try:
                parts = [p for p in request.filter.split(";") if p]
                kv = dict(p.split("=", 1) for p in parts if "=" in p)
                tag_str = kv.get("tag")
                if tag_str:
                    tags = tag_str.split(",")
                if "interval" in kv:
                    interval = int(kv["interval"])
            except Exception:
                tags = []
            if tags and interval:
                queues = set(self._repo.get_queues_by_tag(tags, interval))
                sizes = {k: v for k, v in sizes.items() if k in queues}
        return dagmanager_pb2.QueueStats(sizes=sizes)

    async def RedoDiff(
        self,
        request: dagmanager_pb2.RedoDiffRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.DiffResult:
        if self._diff is None:
            return dagmanager_pb2.DiffResult()
        chunk = self._diff.diff(
            DiffRequest(strategy_id=request.sentinel_id, dag_json=request.dag_json)
        )
        return dagmanager_pb2.DiffResult(
            queue_map=chunk.queue_map, sentinel_id=chunk.sentinel_id
        )


class TagQueryServicer(dagmanager_pb2_grpc.TagQueryServicer):
    def __init__(self, repo: Neo4jNodeRepository) -> None:
        self._repo = repo

    async def GetQueues(
        self,
        request: dagmanager_pb2.TagQueryRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.TagQueryReply:
        queues = self._repo.get_queues_by_tag(request.tags, request.interval)
        return dagmanager_pb2.TagQueryReply(queues=queues)


class HealthServicer(dagmanager_pb2_grpc.HealthCheckServicer):
    def __init__(self, driver) -> None:
        self._driver = driver

    async def Status(
        self,
        request: dagmanager_pb2.StatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.StatusReply:
        info = get_status(self._driver)
        return dagmanager_pb2.StatusReply(
            neo4j=info.get("neo4j", "unknown"),
            state=info.get("dag_manager", "unknown"),
        )


def serve(
    neo4j_driver,
    kafka_admin_client,
    stream_sender: StreamSender,
    *,
    host: str = "0.0.0.0",
    port: int = 50051,
    callback_url: str | None = None,
    gc: GarbageCollector | None = None,
) -> tuple[grpc.aio.Server, int]:
    repo = Neo4jNodeRepository(neo4j_driver)
    admin = KafkaAdmin(kafka_admin_client)
    queue = KafkaQueueManager(admin)
    diff_service = DiffService(repo, queue, stream_sender)

    server = grpc.aio.server()
    dagmanager_pb2_grpc.add_DiffServiceServicer_to_server(
        DiffServiceServicer(diff_service, callback_url), server
    )
    dagmanager_pb2_grpc.add_TagQueryServicer_to_server(
        TagQueryServicer(repo), server
    )
    dagmanager_pb2_grpc.add_AdminServiceServicer_to_server(
        AdminServiceServicer(gc, admin, repo, diff=diff_service, callback_url=callback_url), server
    )
    dagmanager_pb2_grpc.add_HealthCheckServicer_to_server(
        HealthServicer(neo4j_driver), server
    )
    bound_port = server.add_insecure_port(f"{host}:{port}")
    return server, bound_port

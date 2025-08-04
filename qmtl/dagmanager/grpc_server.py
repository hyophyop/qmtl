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
    NodeRepository,
    QueueManager,
)
from .kafka_admin import KafkaAdmin
from qmtl.common import AsyncCircuitBreaker
from .callbacks import post
from ..common.cloudevents import format_event
from .gc import GarbageCollector
from ..proto import dagmanager_pb2, dagmanager_pb2_grpc
from .dagmanager_health import get_health


class _GrpcStream(StreamSender):
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[DiffChunk | None] = asyncio.Queue()
        self._ack = threading.Event()

    def send(self, chunk: DiffChunk) -> None:
        fut = asyncio.run_coroutine_threadsafe(self.queue.put(chunk), self.loop)
        fut.result()
        if not self._ack.wait(timeout=30):
            raise TimeoutError("diff chunk ack timeout")
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
        fut = asyncio.create_task(
            svc.diff_async(DiffRequest(strategy_id=request.strategy_id, dag_json=request.dag_json))
        )
        fut.add_done_callback(lambda _fut: stream.queue.put_nowait(None))
        try:
            while True:
                chunk = await stream.queue.get()
                if chunk is None:
                    break
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
                                    "match_mode": "any",
                                },
                            )
                            for attempt in range(3):
                                try:
                                    await post(self._callback_url, event)
                                    break
                                except Exception:
                                    if attempt == 2:
                                        raise
                                    await asyncio.sleep(2**attempt)
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
        repo: NodeRepository | None = None,
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
                                "match_mode": "any",
                            },
                        )
                        for attempt in range(3):
                            try:
                                await post(self._callback_url, event)
                                break
                            except Exception:
                                if attempt == 2:
                                    raise
                                await asyncio.sleep(2**attempt)
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
                queues = set(
                    self._repo.get_queues_by_tag(tags, interval, match_mode="any")
                )
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
    def __init__(self, repo: NodeRepository) -> None:
        self._repo = repo

    async def GetQueues(
        self,
        request: dagmanager_pb2.TagQueryRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.TagQueryReply:
        queues = self._repo.get_queues_by_tag(
            request.tags, request.interval, match_mode=request.match_mode or "any"
        )
        return dagmanager_pb2.TagQueryReply(queues=queues)


class HealthServicer(dagmanager_pb2_grpc.HealthCheckServicer):
    def __init__(self, driver) -> None:
        self._driver = driver

    async def Status(
        self,
        request: dagmanager_pb2.StatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.StatusReply:
        info = get_health(self._driver)
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
    repo: NodeRepository | None = None,
    queue: QueueManager | None = None,
    breaker_threshold: int = 3,
) -> tuple[grpc.aio.Server, int]:
    admin = None
    if kafka_admin_client is not None:
        breaker = AsyncCircuitBreaker(
            max_failures=breaker_threshold,
        )
        admin = KafkaAdmin(kafka_admin_client, breaker=breaker)
    if repo is None:
        repo = Neo4jNodeRepository(neo4j_driver)
    if queue is None and admin is not None:
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

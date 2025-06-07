import asyncio

import grpc
import pytest

from qmtl.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    QueueManager,
    StreamSender,
)
from qmtl.dagmanager.grpc_server import serve
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc


class FakeRepo(NodeRepository):
    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids):
        pass


class FakeQueue(QueueManager):
    def upsert(self, node_id):
        return "topic"


class FakeStream(StreamSender):
    def send(self, chunk):
        pass


@pytest.mark.asyncio
async def test_grpc_diff():
    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    server, port = serve(service, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json="{}")
        responses = [r async for r in stub.Diff(request)]
    await server.stop(None)
    assert responses[0].sentinel_id == "s-sentinel"

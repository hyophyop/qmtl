from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Dict, Iterable

import grpc

from .diff_service import (
    DiffRequest,
    DiffService,
    NodeRepository,
    QueueManager, NodeRecord,
    StreamSender,
)
from ..gateway.dagmanager_client import DagManagerClient
from ..proto import dagmanager_pb2, dagmanager_pb2_grpc


class _MemRepo(NodeRepository):
    def __init__(self) -> None:
        self.records: Dict[str, NodeRecord] = {}
        self.sentinels: list[tuple[str, list[str]]] = []

    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id: str, node_ids) -> None:
        self.sentinels.append((sentinel_id, list(node_ids)))


class _MemQueue(QueueManager):
    def __init__(self) -> None:
        self.topics: Dict[str, str] = {}

    def upsert(self, node_id: str) -> str:
        topic = self.topics.get(node_id)
        if not topic:
            topic = f"topic_{node_id}"
            self.topics[node_id] = topic
        return topic


class _PrintStream(StreamSender):
    def send(self, chunk) -> None:
        print(json.dumps({"queue_map": chunk.queue_map, "sentinel_id": chunk.sentinel_id}))


async def _cmd_diff(args: argparse.Namespace) -> None:
    data = Path(args.file).read_text()
    if args.dry_run:
        service = DiffService(_MemRepo(), _MemQueue(), _PrintStream())
        chunk = service.diff(DiffRequest(strategy_id="cli", dag_json=data))
        print(json.dumps({"queue_map": chunk.queue_map, "sentinel_id": chunk.sentinel_id}))
    else:
        client = DagManagerClient(args.target)
        chunk = await client.diff("cli", data)
        print(json.dumps({"queue_map": dict(chunk.queue_map), "sentinel_id": chunk.sentinel_id}))


async def _cmd_queue_stats(args: argparse.Namespace) -> None:
    channel = grpc.aio.insecure_channel(args.target)
    stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
    req = dagmanager_pb2.QueueStatsRequest(filter=f"tag={args.tag};interval={args.interval}")
    resp = await stub.GetQueueStats(req)
    await channel.close()
    print(json.dumps(dict(resp.sizes)))


async def _cmd_gc(args: argparse.Namespace) -> None:
    channel = grpc.aio.insecure_channel(args.target)
    stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
    await stub.Cleanup(dagmanager_pb2.CleanupRequest(strategy_id=args.sentinel))
    await channel.close()
    print(f"GC triggered for sentinel: {args.sentinel}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qmtl-dagm")
    parser.add_argument("--target", default="localhost:50051", help="gRPC service target")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("diff", help="Run diff")
    p_diff.add_argument("--file", required=True)
    p_diff.add_argument("--dry-run", action="store_true")

    p_stats = sub.add_parser("queue-stats", help="Get queue statistics")
    p_stats.add_argument("--tag", default="")
    p_stats.add_argument("--interval", default="1h")

    p_gc = sub.add_parser("gc", help="Trigger GC for sentinel")
    p_gc.add_argument("--sentinel", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "diff":
        asyncio.run(_cmd_diff(args))
    elif args.cmd == "queue-stats":
        asyncio.run(_cmd_queue_stats(args))
    elif args.cmd == "gc":
        asyncio.run(_cmd_gc(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

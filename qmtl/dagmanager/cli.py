from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
from pathlib import Path
from typing import Dict, Iterable

import grpc
import sys

from .diff_service import (
    DiffRequest,
    DiffService,
    NodeRepository,
    QueueManager,
    NodeRecord,
    StreamSender,
)
from .monitor import AckStatus
from .topic import topic_name
from .neo4j_export import export_schema, connect
from .neo4j_init import init_schema, rollback as neo4j_rollback
from ..gateway.dagmanager_client import DagManagerClient
from ..proto import dagmanager_pb2, dagmanager_pb2_grpc


class _MemRepo(NodeRepository):
    def __init__(self) -> None:
        self.records: Dict[str, NodeRecord] = {}
        self.sentinels: list[tuple[str, list[str]]] = []

    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id: str, node_ids: Iterable[str]) -> None:
        self.sentinels.append((sentinel_id, list(node_ids)))

    def get_queues_by_tag(
        self, tags: Iterable[str], interval: int, match_mode: str = "any"
    ) -> list[dict[str, object]]:
        return []

    def get_node_by_queue(self, queue: str) -> NodeRecord | None:
        for rec in self.records.values():
            if rec.topic == queue:
                return rec
        return None


class _MemQueue(QueueManager):
    def __init__(self) -> None:
        self.topics: Dict[str, str] = {}

    def upsert(
        self,
        asset: str,
        node_type: str,
        code_hash: str,
        version: str,
        *,
        dry_run: bool = False,
    ) -> str:
        key = (asset, node_type, code_hash, version, dry_run)
        topic = self.topics.get(key)
        if not topic:
            topic = topic_name(asset, node_type, code_hash, version, dry_run=dry_run)
            self.topics[key] = topic
        return topic


class _PrintStream(StreamSender):
    def send(self, chunk) -> None:
        print(json.dumps({"queue_map": chunk.queue_map, "sentinel_id": chunk.sentinel_id}))

    def wait_for_ack(self) -> AckStatus:
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK) -> None:
        pass


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Failed to read file '{path}': {e}", file=sys.stderr)
        raise SystemExit(1)


async def _grpc_call(coro):
    try:
        return await coro
    except grpc.RpcError as e:
        print(f"gRPC error: {e}", file=sys.stderr)
        raise SystemExit(1)


async def _cmd_diff(args: argparse.Namespace) -> None:
    data = _read_file(args.file)
    if args.dry_run:
        service = DiffService(_MemRepo(), _MemQueue(), _PrintStream())
        chunk = service.diff(DiffRequest(strategy_id="cli", dag_json=data))
        print(json.dumps({"queue_map": chunk.queue_map, "sentinel_id": chunk.sentinel_id}))
    else:
        client = DagManagerClient(args.target)
        try:
            chunk = await _grpc_call(client.diff("cli", data))
            print(json.dumps({"queue_map": dict(chunk.queue_map), "sentinel_id": chunk.sentinel_id}))
        finally:
            await client.close()


async def _cmd_queue_stats(args: argparse.Namespace) -> None:
    channel = grpc.aio.insecure_channel(args.target)
    try:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        req = dagmanager_pb2.QueueStatsRequest(filter=f"tag={args.tag};interval={args.interval}")
        resp = await _grpc_call(stub.GetQueueStats(req))
        print(json.dumps(dict(resp.sizes)))
    finally:
        await channel.close()


async def _cmd_gc(args: argparse.Namespace) -> None:
    channel = grpc.aio.insecure_channel(args.target)
    try:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        await _grpc_call(stub.Cleanup(dagmanager_pb2.CleanupRequest(strategy_id=args.sentinel)))
        print(f"GC triggered for sentinel: {args.sentinel}")
    finally:
        await channel.close()


async def _cmd_redo_diff(args: argparse.Namespace) -> None:
    data = _read_file(args.file)
    channel = grpc.aio.insecure_channel(args.target)
    try:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        req = dagmanager_pb2.RedoDiffRequest(sentinel_id=args.sentinel, dag_json=data)
        resp = await _grpc_call(stub.RedoDiff(req))
        print(json.dumps({"queue_map": dict(resp.queue_map), "sentinel_id": resp.sentinel_id}))
    finally:
        await channel.close()


def _dag_hash(dag_json: str) -> str:
    """Return a stable hash for the given DAG JSON string."""
    try:
        data = json.loads(dag_json)
    except json.JSONDecodeError as e:
        print(f"Invalid DAG JSON: {e}", file=sys.stderr)
        raise SystemExit(1)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _cmd_snapshot(args: argparse.Namespace) -> None:
    dag_text = _read_file(args.file)
    digest = _dag_hash(dag_text)
    snap_path = Path(args.snapshot)
    if args.freeze:
        snap = {"dag_hash": digest, "dag": json.loads(dag_text)}
        snap_path.write_text(json.dumps(snap, indent=2, sort_keys=True))
        print(digest)
        return
    if args.verify:
        try:
            existing = json.loads(snap_path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"Failed to read snapshot '{snap_path}': {e}", file=sys.stderr)
            raise SystemExit(1)
        if existing.get("dag_hash") != digest:
            print("Snapshot mismatch", file=sys.stderr)
            raise SystemExit(1)
        print("Snapshot OK")
        return
    print(digest)


def _cmd_export_schema(args: argparse.Namespace) -> None:
    driver = connect(args.uri, args.user, args.password)
    try:
        stmts = export_schema(driver)
    finally:
        driver.close()
    text = "\n".join(stmts) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text, end="")


def _cmd_neo4j_init(args: argparse.Namespace) -> None:
    init_schema(args.uri, args.user, args.password)


async def _main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qmtl dagmanager")
    parser.add_argument("--target", help="gRPC service target", default="localhost:50051")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("diff", help="Run diff")
    p_diff.add_argument("--file", required=True)
    p_diff.add_argument("--dry_run", action="store_true")

    p_snap = sub.add_parser("snapshot", help="Create or verify DAG snapshot")
    p_snap.add_argument("--file", required=True)
    p_snap.add_argument("--snapshot", default="dag.snapshot.json")
    g = p_snap.add_mutually_exclusive_group()
    g.add_argument("--freeze", action="store_true", help="Write snapshot file")
    g.add_argument("--verify", action="store_true", help="Verify against snapshot file")

    p_stats = sub.add_parser("queue-stats", help="Get queue statistics")
    p_stats.add_argument("--tag", default="")
    p_stats.add_argument("--interval", default="1h")

    p_gc = sub.add_parser("gc", help="Trigger GC for sentinel")
    p_gc.add_argument("--sentinel", required=True)

    p_rdiff = sub.add_parser("redo-diff", help="Redo diff for sentinel")
    p_rdiff.add_argument("--sentinel", required=True)
    p_rdiff.add_argument("--file", required=True)

    p_exp = sub.add_parser("export-schema", help="Export Neo4j schema")
    p_exp.add_argument("--uri", default="bolt://localhost:7687")
    p_exp.add_argument("--user", default="neo4j")
    p_exp.add_argument("--password", default="neo4j")
    p_exp.add_argument("--out")

    p_init = sub.add_parser("neo4j-init", help="Initialize Neo4j schema")
    p_init.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j connection URI")
    p_init.add_argument("--user", default="neo4j", help="Neo4j username")
    p_init.add_argument("--password", default="neo4j", help="Neo4j password")

    p_rb = sub.add_parser("neo4j-rollback", help="Drop Neo4j constraints/indexes created by init")
    p_rb.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j connection URI")
    p_rb.add_argument("--user", default="neo4j", help="Neo4j username")
    p_rb.add_argument("--password", default="neo4j", help="Neo4j password")

    args = parser.parse_args(argv)

    if args.cmd == "diff":
        await _cmd_diff(args)
    elif args.cmd == "snapshot":
        _cmd_snapshot(args)
    elif args.cmd == "queue-stats":
        await _cmd_queue_stats(args)
    elif args.cmd == "gc":
        await _cmd_gc(args)
    elif args.cmd == "redo-diff":
        await _cmd_redo_diff(args)
    elif args.cmd == "export-schema":
        _cmd_export_schema(args)
    elif args.cmd == "neo4j-init":
        _cmd_neo4j_init(args)
    elif args.cmd == "neo4j-rollback":
        neo4j_rollback(args.uri, args.user, args.password)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

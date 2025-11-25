from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Awaitable, Callable, Dict, Iterable, Sequence

import grpc

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
from qmtl.foundation.proto import dagmanager_pb2, dagmanager_pb2_grpc
from qmtl.utils.i18n import _, set_language


class _MemRepo(NodeRepository):
    def __init__(self) -> None:
        self.records: Dict[str, NodeRecord] = {}
        self.sentinels: list[tuple[str, list[str]]] = []

    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(
        self, sentinel_id: str, node_ids: Iterable[str], version: str
    ) -> None:
        self.sentinels.append((sentinel_id, list(node_ids), version))

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
        namespace: object | None = None,
    ) -> str:
        key = (asset, node_type, code_hash, version, dry_run, namespace)
        topic = self.topics.get(key)
        if not topic:
            topic = topic_name(
                asset,
                node_type,
                code_hash,
                version,
                dry_run=dry_run,
                namespace=namespace,
            )
            self.topics[key] = topic
        return topic


class _PrintStream(StreamSender):
    def send(self, chunk) -> None:
        print(
            json.dumps(
                {
                    "queue_map": chunk.queue_map,
                    "sentinel_id": chunk.sentinel_id,
                    "version": getattr(chunk, "version", ""),
                }
            )
        )

    def wait_for_ack(self) -> AckStatus:
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK) -> None:
        pass


def _read_file(path: str) -> str:
    try:
        return Path(path).read_text()
    except (OSError, UnicodeDecodeError) as e:
        print(
            _("Failed to read file '{path}': {error}").format(path=path, error=e),
            file=sys.stderr,
        )
        raise SystemExit(1)


async def _grpc_call(coro):
    try:
        return await coro
    except grpc.RpcError as e:
        print(_("gRPC error: {error}").format(error=e), file=sys.stderr)
        raise SystemExit(1)


async def _cmd_diff(args: argparse.Namespace) -> None:
    data = _read_file(args.file)
    if args.dry_run:
        service = DiffService(_MemRepo(), _MemQueue(), _PrintStream())
        chunk = service.diff(DiffRequest(strategy_id="cli", dag_json=data))
        print(
            json.dumps(
                {
                    "queue_map": chunk.queue_map,
                    "sentinel_id": chunk.sentinel_id,
                    "version": chunk.version,
                }
            )
        )
    else:
        client = DagManagerClient(args.target)
        try:
            chunk = await _grpc_call(client.diff("cli", data))
            print(
                json.dumps(
                    {
                        "queue_map": dict(chunk.queue_map),
                        "sentinel_id": chunk.sentinel_id,
                        "version": chunk.version,
                    }
                )
            )
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
        print(_("GC triggered for sentinel: {sentinel}").format(sentinel=args.sentinel))
    finally:
        await channel.close()


async def _cmd_redo_diff(args: argparse.Namespace) -> None:
    data = _read_file(args.file)
    channel = grpc.aio.insecure_channel(args.target)
    try:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        req = dagmanager_pb2.RedoDiffRequest(sentinel_id=args.sentinel, dag_json=data)
        resp = await _grpc_call(stub.RedoDiff(req))
        print(
            json.dumps(
                {
                    "queue_map": dict(resp.queue_map),
                    "sentinel_id": resp.sentinel_id,
                    "version": getattr(resp, "version", ""),
                }
            )
        )
    finally:
        await channel.close()


def _dag_hash(dag_json: str) -> str:
    """Return a stable hash for the given DAG JSON string."""
    try:
        data = json.loads(dag_json)
    except json.JSONDecodeError as e:
        print(_("Invalid DAG JSON: {error}").format(error=e), file=sys.stderr)
        raise SystemExit(1)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _extract_lang(argv: Sequence[str]) -> tuple[list[str], str | None]:
    """Return remaining argv and detected --lang/-L value."""

    rest: list[str] = []
    lang: str | None = None

    i = 0
    tokens = list(argv)
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--lang="):
            lang = token.split("=", 1)[1]
            i += 1
            continue
        if token in {"--lang", "-L"}:
            if i + 1 < len(tokens):
                lang = tokens[i + 1]
                i += 2
                continue
            i += 1
            continue
        rest.append(token)
        i += 1
    return rest, lang


def _prepare_language(argv: list[str], original_is_none: bool) -> list[str]:
    raw_argv, lang = _extract_lang(argv)
    if lang is not None:
        set_language(lang)
    elif original_is_none:
        set_language(None)
    return raw_argv


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtl service dagmanager",
        description=_("Operate DAG Manager services and utilities."),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("diff", help=_("Run diff"))
    p_diff.add_argument("--file", required=True, help=_("Path to DAG JSON file"))
    p_diff.add_argument("--dry-run", action="store_true", help=_("Run locally without gRPC"))
    p_diff.add_argument(
        "--target",
        help=_("gRPC service target"),
        default="localhost:50051",
    )

    p_snap = sub.add_parser("snapshot", help=_("Create or verify DAG snapshot"))
    p_snap.add_argument("--file", required=True, help=_("Path to DAG JSON file"))
    p_snap.add_argument(
        "--snapshot",
        default="dag.snapshot.json",
        help=_("Snapshot file path"),
    )
    g = p_snap.add_mutually_exclusive_group()
    g.add_argument("--freeze", action="store_true", help=_("Write snapshot file"))
    g.add_argument(
        "--verify", action="store_true", help=_("Verify against snapshot file")
    )

    p_stats = sub.add_parser("queue-stats", help=_("Get queue statistics"))
    p_stats.add_argument("--tag", default="", help=_("Filter tag"))
    p_stats.add_argument("--interval", default="1h", help=_("Time interval filter"))
    p_stats.add_argument(
        "--target",
        help=_("gRPC service target"),
        default="localhost:50051",
    )

    p_gc = sub.add_parser("gc", help=_("Trigger GC for sentinel"))
    p_gc.add_argument("--sentinel", required=True, help=_("Sentinel identifier"))
    p_gc.add_argument(
        "--target",
        help=_("gRPC service target"),
        default="localhost:50051",
    )

    p_rdiff = sub.add_parser("redo-diff", help=_("Redo diff for sentinel"))
    p_rdiff.add_argument(
        "--sentinel", required=True, help=_("Sentinel identifier")
    )
    p_rdiff.add_argument("--file", required=True, help=_("Path to DAG JSON file"))
    p_rdiff.add_argument(
        "--target",
        help=_("gRPC service target"),
        default="localhost:50051",
    )

    p_exp = sub.add_parser("export-schema", help=_("Export Neo4j schema"))
    p_exp.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help=_("Neo4j connection URI"),
    )
    p_exp.add_argument("--user", default="neo4j", help=_("Neo4j username"))
    p_exp.add_argument("--password", default="neo4j", help=_("Neo4j password"))
    p_exp.add_argument("--out", help=_("Output file path"))

    p_init = sub.add_parser("neo4j-init", help=_("Initialize Neo4j schema"))
    p_init.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help=_("Neo4j connection URI"),
    )
    p_init.add_argument("--user", default="neo4j", help=_("Neo4j username"))
    p_init.add_argument("--password", default="neo4j", help=_("Neo4j password"))

    p_rb = sub.add_parser(
        "neo4j-rollback",
        help=_("Drop Neo4j constraints/indexes created by init"),
    )
    p_rb.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help=_("Neo4j connection URI"),
    )
    p_rb.add_argument("--user", default="neo4j", help=_("Neo4j username"))
    p_rb.add_argument("--password", default="neo4j", help=_("Neo4j password"))

    p_server = sub.add_parser("server", help=_("Run DAG Manager gRPC/HTTP services"))
    p_server.add_argument("--config", help=_("Path to configuration file"))

    p_metrics = sub.add_parser(
        "metrics", help=_("Expose DAG Manager Prometheus metrics")
    )
    p_metrics.add_argument(
        "--port",
        type=int,
        default=8000,
        help=_("Port to expose metrics on"),
    )

    return parser


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
            print(
                _("Failed to read snapshot '{path}': {error}").format(
                    path=snap_path, error=e
                ),
                file=sys.stderr,
            )
            raise SystemExit(1)
        if existing.get("dag_hash") != digest:
            print(_("Snapshot mismatch"), file=sys.stderr)
            raise SystemExit(1)
        print(_("Snapshot OK"))
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


def _run_server(args: argparse.Namespace) -> None:
    from .server import main as server_main

    server_args: list[str] = []
    if args.config:
        server_args.extend(["--config", args.config])
    server_main(server_args)


def _run_metrics(args: argparse.Namespace) -> None:
    from .metrics import main as metrics_main

    metrics_main(["--port", str(args.port)])


CommandHandler = Callable[[argparse.Namespace], Awaitable[None] | None]

_COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "diff": _cmd_diff,
    "snapshot": _cmd_snapshot,
    "queue-stats": _cmd_queue_stats,
    "gc": _cmd_gc,
    "redo-diff": _cmd_redo_diff,
    "export-schema": _cmd_export_schema,
    "neo4j-init": _cmd_neo4j_init,
    "neo4j-rollback": lambda args: neo4j_rollback(args.uri, args.user, args.password),
    "server": _run_server,
    "metrics": _run_metrics,
}


async def _dispatch_command(args: argparse.Namespace) -> None:
    handler = _COMMAND_HANDLERS.get(args.cmd)
    if handler is None:
        raise SystemExit(1)
    result = handler(args)
    if inspect.isawaitable(result):
        await result


async def _main(argv: list[str] | None = None) -> None:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized_argv = _prepare_language(raw_argv, argv is None)

    parser = _build_parser()
    args = parser.parse_args(normalized_argv)

    await _dispatch_command(args)


def main(argv: list[str] | None = None) -> None:
    asyncio.run(_main(argv))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

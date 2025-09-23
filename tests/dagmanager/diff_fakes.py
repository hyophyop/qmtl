"""Reusable fake implementations for diff service tests."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from qmtl.services.dagmanager.diff_service import NodeRepository, QueueManager, StreamSender
from qmtl.services.dagmanager.monitor import AckStatus
from qmtl.services.dagmanager.topic import topic_name


class FakeRepo(NodeRepository):
    """In-memory repository that records interactions for assertions."""

    def __init__(self):
        self.fetched: list[list[str]] = []
        self.sentinels: list[tuple[str, list[str], str]] = []
        self.records: dict[str, Any] = {}
        self.buffered: dict[str, dict[str, int]] = {}

    def get_nodes(self, node_ids: Iterable[str]):
        ids = list(node_ids)
        self.fetched.append(ids)
        return {nid: self.records[nid] for nid in ids if nid in self.records}

    def insert_sentinel(self, sentinel_id: str, node_ids: Iterable[str], version: str):
        self.sentinels.append((sentinel_id, list(node_ids), version))

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def mark_buffering(self, node_id, *, compute_key=None, timestamp_ms=None):
        key = compute_key or "__global__"
        self.buffered.setdefault(node_id, {})[key] = timestamp_ms or 0

    def clear_buffering(self, node_id, *, compute_key=None):
        if compute_key:
            ctx = self.buffered.get(node_id)
            if isinstance(ctx, dict):
                ctx.pop(compute_key, None)
                if not ctx:
                    self.buffered.pop(node_id, None)
        else:
            self.buffered.pop(node_id, None)

    def get_buffering_nodes(self, older_than_ms, *, compute_key=None):
        result: list[str] = []
        for node_id, ctx in self.buffered.items():
            if isinstance(ctx, dict):
                if compute_key:
                    ts = ctx.get(compute_key)
                    if ts is not None and ts < older_than_ms:
                        result.append(node_id)
                elif any(ts is not None and ts < older_than_ms for ts in ctx.values()):
                    result.append(node_id)
            else:
                if ctx < older_than_ms:
                    result.append(node_id)
        return result


class FakeQueue(QueueManager):
    def __init__(self):
        self.calls: list[tuple[str, str, str, str, bool, str | None]] = []

    def upsert(
        self,
        asset,
        node_type,
        code_hash,
        version,
        *,
        dry_run=False,
        namespace=None,
    ):
        call = (asset, node_type, code_hash, version, dry_run, namespace)
        self.calls.append(call)
        return topic_name(
            asset,
            node_type,
            code_hash,
            version,
            dry_run=dry_run,
            namespace=namespace,
        )


class FakeStream(StreamSender):
    def __init__(self):
        self.chunks: list[Any] = []
        self.waits = 0

    def send(self, chunk):
        self.chunks.append(chunk)

    def wait_for_ack(self) -> AckStatus:
        self.waits += 1
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
        pass


class TimeoutOnceStream(StreamSender):
    """Stream that times out on the first wait before acknowledging."""

    def __init__(self):
        self.chunks: list[Any] = []
        self.waits = 0
        self.resumes = 0

    def send(self, chunk):
        self.chunks.append(chunk)

    def wait_for_ack(self) -> AckStatus:
        self.waits += 1
        return AckStatus.TIMEOUT if self.waits == 1 else AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
        pass

    def resume_from_last_offset(self):
        self.resumes += 1


class FakeSession:
    def __init__(self, records: list[dict[str, Any]] | None = None):
        self.records = records or []
        self.run_calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params):
        self.run_calls.append((query, params))
        return self.records

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDriver:
    def __init__(self, records: list[dict[str, Any]] | None = None):
        self.session_obj = FakeSession(records)

    def session(self):
        return self.session_obj


class FakeAdmin:
    def __init__(self, topics: dict[str, Any] | None = None):
        self.created: list[tuple[str, int, int, dict[str, Any] | None]] = []
        self.topics = topics or {}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        self.created.append((name, num_partitions, replication_factor, config))


__all__ = [
    "FakeAdmin",
    "FakeDriver",
    "FakeQueue",
    "FakeRepo",
    "FakeSession",
    "FakeStream",
    "TimeoutOnceStream",
]

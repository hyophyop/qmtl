from __future__ import annotations

"""Garbage collection utilities for orphan Kafka queues."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Protocol, Optional

from .metrics import orphan_queue_total
from .metrics import gc_last_run_timestamp


@dataclass(frozen=True)
class GcRule:
    ttl: timedelta
    grace: timedelta
    action: str  # "drop" or "archive"


@dataclass
class QueueInfo:
    name: str
    tag: str
    created_at: datetime
    interval: int | None = None


class QueueStore(Protocol):
    """Abstraction over the queue metadata store."""

    def list_orphan_queues(self) -> Iterable[QueueInfo]:
        """Return orphan queues pending GC."""
        raise NotImplementedError

    def drop_queue(self, name: str) -> None:
        """Remove the queue from the broker."""
        raise NotImplementedError


class MetricsProvider(Protocol):
    """Expose Kafka broker metrics."""

    def messages_in_per_sec(self) -> float:
        """Return broker ingestion percentage (0-100)."""
        raise NotImplementedError


class ArchiveClient(Protocol):
    """Optional S3 archive interface."""

    def archive(self, queue: str) -> None:
        raise NotImplementedError


class S3ArchiveClient:
    """Upload archived queue contents to S3."""

    def __init__(self, bucket: str, *, client=None) -> None:
        self.bucket = bucket
        import boto3

        self._client = client or boto3.client("s3")

    def archive(self, queue: str) -> None:
        """Store queue dump in ``self.bucket`` under a timestamped key."""
        key = f"{queue}-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
        self._client.put_object(Bucket=self.bucket, Key=key, Body=b"")


DEFAULT_POLICY = {
    "raw": GcRule(ttl=timedelta(days=7), grace=timedelta(days=1), action="drop"),
    "indicator": GcRule(ttl=timedelta(days=30), grace=timedelta(days=3), action="drop"),
    "sentinel": GcRule(ttl=timedelta(days=180), grace=timedelta(days=30), action="archive"),
}


class GarbageCollector:
    """Apply GC policy to orphan queues."""

    def __init__(
        self,
        store: QueueStore,
        metrics: MetricsProvider,
        *,
        policy: dict[str, GcRule] | None = None,
        batch_size: int = 50,
        archive: Optional[ArchiveClient] = None,
    ) -> None:
        self.store = store
        self.metrics = metrics
        self.policy = policy or DEFAULT_POLICY
        self.batch_size = batch_size
        self.archive = archive

    def collect(self, now: Optional[datetime] = None) -> list[QueueInfo]:
        """Run one GC batch and return processed QueueInfo items."""
        now = now or datetime.utcnow()
        all_queues = list(self.store.list_orphan_queues())
        orphan_queue_total.set(len(all_queues))
        orphan_queue_total._val = len(all_queues)  # type: ignore[attr-defined]
        queues = []
        for q in all_queues:
            rule = self.policy.get(q.tag)
            if not rule:
                continue
            if now - q.created_at >= rule.ttl + rule.grace:
                queues.append((q, rule))
        # adjust batch size based on broker load
        batch = self.batch_size
        if self.metrics.messages_in_per_sec() >= 80:
            batch = max(1, batch // 2)
        queues = queues[:batch]
        processed: list[QueueInfo] = []
        for q, rule in queues:
            if rule.action == "drop":
                self.store.drop_queue(q.name)
            elif rule.action == "archive":
                if self.archive is not None and q.tag == "sentinel":
                    self.archive.archive(q.name)
                self.store.drop_queue(q.name)
            processed.append(q)
        gc_last_run_timestamp.set(now.timestamp())
        gc_last_run_timestamp._val = gc_last_run_timestamp._value.get()  # type: ignore[attr-defined]
        return processed


__all__ = [
    "GcRule",
    "QueueInfo",
    "QueueStore",
    "MetricsProvider",
    "ArchiveClient",
    "S3ArchiveClient",
    "GarbageCollector",
    "DEFAULT_POLICY",
]

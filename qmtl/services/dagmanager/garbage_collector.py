"""Garbage collection utilities for orphan Kafka queues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable, Optional, Protocol

from .metrics import gc_last_run_timestamp, orphan_queue_total


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


@dataclass(frozen=True)
class CleanupReportItem:
    queue: str
    tag: str
    interval: int | None
    action: str
    reason: str
    archive_status: str | None = None


@dataclass(frozen=True)
class CleanupReport:
    observed: int
    candidates: int
    processed: list[QueueInfo]
    skipped: list[CleanupReportItem]
    actions: dict[str, int]
    by_tag: dict[str, int]
    items: list[CleanupReportItem]

    def to_dict(self) -> dict[str, object]:
        return {
            "observed": self.observed,
            "candidates": self.candidates,
            "processed": [q.name for q in self.processed],
            "skipped": [item.__dict__ for item in self.skipped],
            "actions": dict(self.actions),
            "by_tag": dict(self.by_tag),
            "items": [item.__dict__ for item in self.items],
        }


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
        if client is None:
            import boto3

            self._client = boto3.client("s3")
        else:
            self._client = client

    def archive(self, queue: str) -> None:
        """Store queue dump in ``self.bucket`` under a timestamped key."""
        key = f"{queue}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
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
        return self.collect_report(now).processed

    def collect_report(self, now: Optional[datetime] = None) -> CleanupReport:
        """Run one GC batch and return a structured cleanup report."""
        now = now or datetime.now(UTC)
        all_queues = list(self.store.list_orphan_queues())
        self._record_orphan_count(all_queues)

        candidates, skipped = self._select_candidates(all_queues, now)
        batch = self._adjust_batch_size()
        processed, processed_items, process_skips = self._process_batch(candidates[:batch])
        skipped.extend(process_skips)

        gc_last_run_timestamp.set(now.timestamp())
        gc_last_run_timestamp._val = gc_last_run_timestamp._value.get()  # type: ignore[attr-defined]
        items = processed_items + skipped
        return CleanupReport(
            observed=len(all_queues),
            candidates=len(candidates),
            processed=processed,
            skipped=skipped,
            actions=self._count_actions(items),
            by_tag=self._count_by_tag(all_queues),
            items=items,
        )

    def _record_orphan_count(self, queues: list[QueueInfo]) -> None:
        orphan_queue_total.set(len(queues))
        orphan_queue_total._val = len(queues)  # type: ignore[attr-defined]

    def _select_candidates(
        self, queues: list[QueueInfo], now: datetime
    ) -> tuple[list[tuple[QueueInfo, GcRule]], list[CleanupReportItem]]:
        candidates: list[tuple[QueueInfo, GcRule]] = []
        skipped: list[CleanupReportItem] = []
        for queue in queues:
            rule = self.policy.get(queue.tag)
            if not rule:
                skipped.append(self._report_item(queue, "skip", "unknown_policy"))
                continue
            if now - queue.created_at >= rule.ttl + rule.grace:
                candidates.append((queue, rule))
            else:
                skipped.append(self._report_item(queue, "skip", "within_grace"))
        return candidates, skipped

    def _adjust_batch_size(self) -> int:
        if self.metrics.messages_in_per_sec() >= 80:
            return max(1, self.batch_size // 2)
        return self.batch_size

    def _process_batch(
        self, queues: list[tuple[QueueInfo, GcRule]]
    ) -> tuple[list[QueueInfo], list[CleanupReportItem], list[CleanupReportItem]]:
        processed: list[QueueInfo] = []
        processed_items: list[CleanupReportItem] = []
        skipped: list[CleanupReportItem] = []
        for queue, rule in queues:
            if rule.action == "drop":
                self.store.drop_queue(queue.name)
                processed_items.append(self._report_item(queue, "drop", "eligible"))
            elif rule.action == "archive":
                if self.archive is not None:
                    try:
                        self.archive.archive(queue.name)
                    except Exception:
                        skipped.append(
                            self._report_item(
                                queue,
                                "skip",
                                "archive_failed",
                                archive_status="failed",
                            )
                        )
                        continue
                    archive_status = "archived"
                else:
                    archive_status = "missing_client"
                self.store.drop_queue(queue.name)
                processed_items.append(
                    self._report_item(
                        queue,
                        "archive",
                        "eligible",
                        archive_status=archive_status,
                    )
                )
            processed.append(queue)
        return processed, processed_items, skipped

    @staticmethod
    def _report_item(
        queue: QueueInfo,
        action: str,
        reason: str,
        *,
        archive_status: str | None = None,
    ) -> CleanupReportItem:
        return CleanupReportItem(
            queue=queue.name,
            tag=queue.tag,
            interval=queue.interval,
            action=action,
            reason=reason,
            archive_status=archive_status,
        )

    @staticmethod
    def _count_actions(items: list[CleanupReportItem]) -> dict[str, int]:
        counts = {"drop": 0, "archive": 0, "skip": 0}
        for item in items:
            counts[item.action] = counts.get(item.action, 0) + 1
        return counts

    @staticmethod
    def _count_by_tag(queues: list[QueueInfo]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for queue in queues:
            counts[queue.tag] = counts.get(queue.tag, 0) + 1
        return counts


__all__ = [
    "GcRule",
    "QueueInfo",
    "CleanupReport",
    "CleanupReportItem",
    "QueueStore",
    "MetricsProvider",
    "ArchiveClient",
    "S3ArchiveClient",
    "GarbageCollector",
    "DEFAULT_POLICY",
]

"""Reusable test doubles for service-layer contract and collaboration tests.

These helpers keep service suites focused on observable behaviours—messages
emitted, collaborator invocations, configuration hand-offs—without reaching
into private attributes or Prometheus internals. They intentionally mirror the
shape of the concrete collaborators used by Gateway, DagManager, and
WorldService so suites can express expectations with minimal monkeypatching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class RecordingCommitLogProducer:
    """Minimal async producer that records commit-log messages."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    began: int = 0
    committed: int = 0
    aborted: int = 0

    async def begin_transaction(self) -> None:  # pragma: no cover - simple bookkeeping
        self.began += 1

    async def send_and_wait(
        self,
        topic: str,
        *,
        key: bytes | None = None,
        value: bytes | None = None,
        headers: Sequence[tuple[str, bytes]] | None = None,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
                "headers": tuple(headers or ()),
            }
        )

    async def commit_transaction(self) -> None:  # pragma: no cover - simple bookkeeping
        self.committed += 1

    async def abort_transaction(self) -> None:  # pragma: no cover - simple bookkeeping
        self.aborted += 1


@dataclass
class FakeKafkaMessage:
    """Lightweight structure mimicking an ``aiokafka`` message."""

    value: bytes


@dataclass
class RecordingCommitLogConsumerBackend:
    """Test double that feeds predefined batches to ``CommitLogConsumer``."""

    batches: list[list[FakeKafkaMessage]]
    commit_calls: int = 0
    started: bool = False
    stopped: bool = False

    async def start(self) -> None:  # pragma: no cover - trivial
        self.started = True

    async def stop(self) -> None:  # pragma: no cover - trivial
        self.stopped = True

    async def getmany(self, timeout_ms: int | None = None) -> Dict[None, List[FakeKafkaMessage]]:
        if self.batches:
            return {None: self.batches.pop(0)}
        return {}

    async def commit(self) -> None:  # pragma: no cover - trivial
        self.commit_calls += 1


class SpyTradeDispatcher:
    """Capture trade orders dispatched by Runner without touching sinks."""

    def __init__(self) -> None:
        self.orders: list[Any] = []
        self.http_urls: list[Optional[str]] = []
        self.kafka_topic: Optional[str] = None
        self.kafka_producer: Any = None
        self.execution_service: Any = None
        self.activation_manager: Any = None
        self.dedup_reset_count = 0

    def dispatch(self, order: Any) -> None:
        self.orders.append(order)

    def set_http_url(self, url: Optional[str]) -> None:
        self.http_urls.append(url)

    def set_kafka_producer(self, producer: Any | None) -> None:
        self.kafka_producer = producer

    def set_trade_order_kafka_topic(self, topic: Optional[str]) -> None:
        self.kafka_topic = topic

    def set_trade_execution_service(self, service: Any | None) -> None:
        self.execution_service = service

    def set_activation_manager(self, manager: Any | None) -> None:
        self.activation_manager = manager

    def reset_dedup(self) -> None:
        self.dedup_reset_count += 1


class SpyHistoryService:
    """Record history warm-up interactions initiated by Runner."""

    def __init__(self) -> None:
        self.warmup_calls: list[dict[str, Any]] = []
        self.write_calls: list[Any] = []

    async def warmup_strategy(
        self,
        strategy: Any,
        *,
        offline_mode: bool,
        history_start: Any | None,
        history_end: Any | None,
    ) -> None:
        self.warmup_calls.append(
            {
                "strategy": strategy,
                "offline_mode": offline_mode,
                "history_start": history_start,
                "history_end": history_end,
            }
        )

    def write_snapshots(self, strategy: Any) -> None:
        self.write_calls.append(strategy)


class NullFeaturePlane:
    """Feature artifact plane that simply records the payloads it sees."""

    def __init__(self) -> None:
        self.records: list[tuple[Any, int, Any]] = []

    def record(self, factor: Any, timestamp: int, payload: Any) -> None:
        self.records.append((factor, timestamp, payload))


__all__ = [
    "RecordingCommitLogProducer",
    "FakeKafkaMessage",
    "RecordingCommitLogConsumerBackend",
    "SpyTradeDispatcher",
    "SpyHistoryService",
    "NullFeaturePlane",
]

from __future__ import annotations

"""Simple Kafka Admin wrapper for idempotent topic creation."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Protocol

from qmtl.foundation.common import AsyncCircuitBreaker, ComputeContext, compute_compute_key
from . import metrics

from .topic import TopicConfig


def compute_key(
    node_id: str,
    *,
    world_id: str | None = None,
    execution_domain: str | None = None,
    as_of: str | None = None,
    partition: str | None = None,
    dataset_fingerprint: str | None = None,
) -> str:
    """Return the domain-scoped compute key for ``node_id``.

    The helper mirrors :func:`qmtl.foundation.common.compute_compute_key` so that
    cache/topic isolation semantics remain aligned with the documented
    architecture. ``dataset_fingerprint`` is accepted for compatibility but
    does not affect the resulting key – callers relying on dataset-level
    isolation should include the fingerprint in their node identifiers.
    """

    context = ComputeContext().with_world(world_id)
    context = context.with_overrides(
        execution_domain=execution_domain,
        as_of=as_of,
        partition=partition,
        dataset_fingerprint=dataset_fingerprint,
    )
    return compute_compute_key(node_id, context)


def partition_key(
    node_id: str,
    interval: int | None,
    bucket: int | None,
    *,
    compute_key: str | None = None,
) -> str:
    """Return a stable partition key for Kafka operations.

    ``interval`` and ``bucket`` may be ``None`` which is normal for nodes that
    do not operate on a fixed schedule. ``None`` values are normalised to ``0``
    so that the resulting key is always a simple ``":"`` separated string.
    """
    base = f"{node_id}:{interval or 0}:{bucket or 0}"
    if compute_key:
        return f"{base}#ck={compute_key}"
    return base


class TopicExistsError(Exception):
    """Raised when attempting to create a topic that already exists."""


class AdminClient(Protocol):
    """Protocol describing minimal Kafka admin client methods."""

    def list_topics(self) -> Mapping[str, dict]:
        ...

    def create_topic(
        self,
        name: str,
        *,
        num_partitions: int,
        replication_factor: int,
        config: Mapping[str, str] | None = None,
    ) -> None:
        ...


class InMemoryAdminClient:
    """Simple in-memory implementation of :class:`AdminClient`."""

    def __init__(self) -> None:
        self.topics: Dict[str, dict] = {}

    def list_topics(self) -> Mapping[str, dict]:
        return self.topics

    def create_topic(
        self,
        name: str,
        *,
        num_partitions: int,
        replication_factor: int,
        config: Mapping[str, str] | None = None,
    ) -> None:
        if name in self.topics:
            raise TopicExistsError
        self.topics[name] = {
            "config": dict(config or {}),
            "num_partitions": num_partitions,
            "replication_factor": replication_factor,
            "size": 0,
            "created_at": int(time.time()),
        }

    def get_size(self, name: str) -> int:
        return int(self.topics.get(name, {}).get("size", 0))

    def set_offsets(self, name: str, *, high: int, low: int = 0) -> None:
        if name in self.topics:
            self.topics[name]["offsets"] = {"high": high, "low": low}

    def delete_topic(self, name: str) -> None:
        self.topics.pop(name, None)


@dataclass
class TopicEnsureResult:
    """Result of ensuring a topic exists and matches the requested config."""

    ok: bool
    error: Exception | None = None
    collisions: list[str] = field(default_factory=list)
    diagnostics: dict[str, object] = field(default_factory=dict)

    @classmethod
    def success(cls, diagnostics: dict[str, object] | None = None) -> "TopicEnsureResult":
        return cls(True, None, [], diagnostics or {})

    @classmethod
    def failure(
        cls,
        error: Exception | None,
        *,
        collisions: list[str] | None = None,
        diagnostics: dict[str, object] | None = None,
    ) -> "TopicEnsureResult":
        return cls(False, error, collisions or [], diagnostics or {})


@dataclass
class TopicVerificationPolicy:
    """Policy for validating broker metadata for a topic."""

    def evaluate(
        self, name: str, metadata: Mapping[str, dict], config: TopicConfig
    ) -> TopicEnsureResult:
        collisions = self._find_collisions(name, metadata)
        if collisions:
            return TopicEnsureResult.failure(
                TopicExistsError(f"name collision for topic '{name}'"),
                collisions=collisions,
                diagnostics={"collisions": collisions},
            )

        info = metadata.get(name)
        if not isinstance(info, Mapping):
            return TopicEnsureResult.failure(None, diagnostics={"reason": "missing"})

        config_result = self._validate_metadata(name, info, config)
        if config_result is not None:
            return config_result

        return TopicEnsureResult.success({"reason": "verified"})

    def _find_collisions(
        self, name: str, metadata: Mapping[str, dict]
    ) -> list[str]:  # pragma: no cover - trivial
        return [
            existing
            for existing in metadata
            if existing.lower() == name.lower() and existing != name
        ]

    def _validate_metadata(
        self, name: str, info: Mapping[str, object], config: TopicConfig
    ) -> TopicEnsureResult | None:
        partitions = info.get("num_partitions")
        if partitions is not None and int(partitions) != config.partitions:
            return TopicEnsureResult.failure(
                TopicExistsError(f"partition mismatch for topic '{name}'"),
                diagnostics={"partitions": partitions},
            )

        replication = info.get("replication_factor")
        if replication is not None and int(replication) != config.replication_factor:
            return TopicEnsureResult.failure(
                TopicExistsError(f"replication mismatch for topic '{name}'"),
                diagnostics={"replication_factor": replication},
            )

        meta_config = info.get("config")
        if isinstance(meta_config, Mapping):
            retention = meta_config.get("retention.ms")
            if retention is not None and int(retention) != int(config.retention_ms):
                return TopicEnsureResult.failure(
                    TopicExistsError(f"retention mismatch for topic '{name}'"),
                    diagnostics={"retention.ms": retention},
                )
        return None


@dataclass
class RetryStep:
    attempt: int
    delay: float
    is_last: bool


@dataclass
class TopicCreateRetryStrategy:
    """Strategy object for retry/backoff orchestration."""

    attempts: int
    initial_delay: float
    max_delay: float
    multiplier: float

    def plan(self) -> Iterable[RetryStep]:
        total_attempts = max(1, int(self.attempts))
        delay = max(0.0, float(self.initial_delay))
        cap = max(delay, float(self.max_delay))

        for attempt in range(1, total_attempts + 1):
            yield RetryStep(attempt, delay, attempt == total_attempts)
            if self.multiplier > 0 and not attempt == total_attempts:
                delay = min(cap, max(0.0, delay * float(self.multiplier)))


@dataclass
class KafkaAdmin:
    client: AdminClient
    breaker: AsyncCircuitBreaker = field(default_factory=AsyncCircuitBreaker)
    max_attempts: int = 5
    wait_initial: float = 0.5
    wait_max: float = 4.0
    backoff_multiplier: float = 2.0
    verification_policy: TopicVerificationPolicy = field(
        default_factory=TopicVerificationPolicy
    )

    def __post_init__(self) -> None:
        """Attach metric callbacks without overriding existing hooks."""
        prev_on_open = self.breaker._on_open

        def _on_open() -> None:
            if prev_on_open is not None:
                prev_on_open()
            metrics.kafka_breaker_open_total.inc()

        self.breaker._on_open = _on_open

    def _verify_topic(self, name: str, config: TopicConfig) -> TopicEnsureResult:
        """Return verification result for ``name`` using broker metadata."""

        metadata = self.client.list_topics()
        return self.verification_policy.evaluate(name, metadata, config)

    def _build_retry_strategy(self) -> TopicCreateRetryStrategy:
        return TopicCreateRetryStrategy(
            attempts=self.max_attempts,
            initial_delay=self.wait_initial,
            max_delay=self.wait_max,
            multiplier=self.backoff_multiplier,
        )

    def _create_topic(self, name: str, config: TopicConfig) -> None:
        self.client.create_topic(
            name,
            num_partitions=config.partitions,
            replication_factor=config.replication_factor,
            config={"retention.ms": str(config.retention_ms)},
        )

    def create_topic_if_needed(self, name: str, config: TopicConfig) -> None:
        """Create topic idempotently using a circuit breaker."""

        strategy = self._build_retry_strategy()

        @self.breaker
        async def _create() -> None:
            last_error: Exception | None = None
            skip_create = False

            for step in strategy.plan():
                if not skip_create:
                    try:
                        self._create_topic(name, config)
                        last_error = None
                    except TopicExistsError as exc:
                        skip_create = True
                        last_error = exc
                    except Exception as exc:  # pragma: no cover - defensive guard
                        last_error = exc

                result = self._verify_topic(name, config)
                if result.ok:
                    return
                if isinstance(result.error, TopicExistsError):
                    raise result.error
                if result.error is not None:
                    last_error = result.error

                if step.is_last:
                    break

                await asyncio.sleep(step.delay)

            if last_error is not None:
                raise last_error
            raise RuntimeError(
                f"failed to create topic '{name}' after {strategy.attempts} attempts"
            )

        asyncio.run(_create())

    def delete_topic(self, name: str) -> None:
        """Delete topic if supported by the underlying client."""

        client = self.client
        deleter = getattr(client, "delete_topic", None)
        if callable(deleter):
            deleter(name)
            return
        delete_topics = getattr(client, "delete_topics", None)
        if callable(delete_topics):
            delete_topics([name])
            return
        topics = getattr(client, "topics", None)
        if isinstance(topics, dict):
            topics.pop(name, None)

    def get_topic_sizes(self) -> Dict[str, int]:
        """Return approximate message count per topic."""
        stats: Dict[str, int] = {}
        for name, meta in self.client.list_topics().items():
            size = meta.get("size")
            offsets = meta.get("offsets")
            if size is None and isinstance(offsets, Mapping):
                high = offsets.get("high", 0)
                low = offsets.get("low", 0)
                size = high - low
            if size is not None:
                stats[name] = int(size)
        return stats

    def get_end_offsets(self, topics: Iterable[str]) -> Dict[str, int]:
        """Return high watermark offsets for ``topics``."""
        end: Dict[str, int] = {}
        meta = self.client.list_topics()
        for t in topics:
            info = meta.get(t)
            if not info:
                continue
            offsets = info.get("offsets")
            if isinstance(offsets, Mapping):
                end[t] = int(offsets.get("high", 0))
            else:
                size = info.get("size")
                if size is not None:
                    end[t] = int(size)
        return end

    def topic_lag(self, committed: Mapping[str, int]) -> Dict[str, int]:
        """Compute lag for each topic given committed offsets."""
        end = self.get_end_offsets(committed.keys())
        lags: Dict[str, int] = {}
        for topic, offset in committed.items():
            lags[topic] = max(0, end.get(topic, offset) - offset)
        return lags


__all__ = [
    "KafkaAdmin",
    "AdminClient",
    "TopicExistsError",
    "InMemoryAdminClient",
    "compute_key",
    "partition_key",
]

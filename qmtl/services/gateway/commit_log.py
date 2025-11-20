from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterable

from qmtl.services.dagmanager.kafka_admin import partition_key
from qmtl.runtime.sdk.snapshot import runtime_fingerprint

try:
    from aiokafka import AIOKafkaProducer
except Exception:  # pragma: no cover - aiokafka optional
    AIOKafkaProducer = Any

logger = logging.getLogger(__name__)


class CommitLogWriter:
    """Write commit-log records to a compacted Kafka topic.

    The writer uses a Kafka producer configured for idempotent transactional
    publishing.  Each call to :meth:`publish_bucket` writes all records for a
    bucket within a single transaction which is either committed or aborted.
    """

    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:
        self._producer = producer
        self._topic = topic

    async def publish_submission(
        self,
        strategy_id: str,
        payload: dict[str, Any],
        *,
        timestamp_ms: int | None = None,
    ) -> None:
        """Publish a gateway ingestion record to the commit log.

        The record value follows the same four-element tuple structure used by
        :class:`CommitLogConsumer` so existing consumers can decode mixed
        streams.  The tuple shape is ``("gateway.ingest", ts, strategy_id,
        payload)`` where ``payload`` contains the submission envelope. When
        ``timestamp_ms`` is ``None`` the current epoch milliseconds are used.
        """

        ts_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        value = json.dumps(
            [
                "gateway.ingest",
                ts_ms,
                strategy_id,
                payload,
            ]
        ).encode()
        key = f"ingest:{strategy_id}".encode()
        headers = [("rfp", runtime_fingerprint().encode())]
        await self._producer.begin_transaction()
        try:
            try:
                await self._producer.send_and_wait(
                    self._topic,
                    key=key,
                    value=value,
                    headers=headers,
                )
            except TypeError:  # pragma: no cover - producer without header support
                await self._producer.send_and_wait(
                    self._topic,
                    key=key,
                    value=value,
                )
            await self._producer.commit_transaction()
        except Exception:
            try:
                await self._producer.abort_transaction()
            except Exception:  # pragma: no cover - double failure
                logger.exception("Commit-log abort failed")
            raise

    async def publish_rebalance_batch(
        self,
        batch_id: str,
        payload: dict[str, Any],
        *,
        timestamp_ms: int | None = None,
    ) -> None:
        """Publish a rebalancing batch record to the commit log."""

        ts_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        value = json.dumps(
            [
                "gateway.rebalance",
                ts_ms,
                batch_id,
                payload,
            ]
        ).encode()
        key = f"rebalance:{batch_id}".encode()
        headers = [("rfp", runtime_fingerprint().encode())]
        await self._producer.begin_transaction()
        try:
            try:
                await self._producer.send_and_wait(
                    self._topic,
                    key=key,
                    value=value,
                    headers=headers,
                )
            except TypeError:  # pragma: no cover - producer without header support
                await self._producer.send_and_wait(
                    self._topic,
                    key=key,
                    value=value,
                )
            await self._producer.commit_transaction()
        except Exception:
            try:
                await self._producer.abort_transaction()
            except Exception:  # pragma: no cover - double failure
                logger.exception("Commit-log abort failed")
            raise

    async def publish_bucket(
        self,
        bucket_ts: int,
        interval: int | None,
        records: Iterable[tuple[str, str, Any] | tuple[str, str, Any, str | None]],
    ) -> None:
        """Publish ``records`` for ``interval``/``bucket_ts`` in a transaction.

        Each record is a tuple ``(node_id, input_window_hash, payload, compute_key)``.
        The ``compute_key`` element is optional; when provided it is used to
        derive the Kafka partition key so that commit-log entries remain
        isolated per compute context. The value sent to Kafka contains
        ``(node_id, bucket_ts, input_window_hash, payload)`` serialised as JSON.
        The message key combines the
        :func:`~qmtl.services.dagmanager.kafka_admin.partition_key` for the ``node_id``,
        ``interval`` and ``bucket_ts`` with the ``input_window_hash`` to ensure
        the topic can be compacted.
        """

        await self._producer.begin_transaction()
        try:
            for record in records:
                parts = tuple(record)
                if len(parts) == 4:
                    node_id, input_window_hash, payload, compute_key_hint = parts
                elif len(parts) == 3:
                    node_id, input_window_hash, payload = parts
                    compute_key_hint = None
                else:  # pragma: no cover - defensive argument validation
                    raise ValueError(
                        "Commit-log records must contain 3 or 4 elements"
                    )
                value = json.dumps(
                    (node_id, bucket_ts, input_window_hash, payload)
                ).encode()
                pkey = partition_key(
                    node_id, interval, bucket_ts, compute_key=compute_key_hint
                )
                key = f"{pkey}:{input_window_hash}".encode()
                # Attach runtime fingerprint in Kafka headers when supported
                headers = [("rfp", runtime_fingerprint().encode())]
                try:
                    await self._producer.send_and_wait(
                        self._topic,
                        key=key,
                        value=value,
                        headers=headers,
                    )
                except TypeError:
                    # Fallback for producers that don't accept headers in tests
                    await self._producer.send_and_wait(
                        self._topic,
                        key=key,
                        value=value,
                    )
            await self._producer.commit_transaction()
        except Exception:  # pragma: no cover - defensive log
            try:
                await self._producer.abort_transaction()
            except Exception:  # pragma: no cover - double failure
                logger.exception("Commit-log abort failed")
            raise


async def create_commit_log_writer(
    bootstrap_servers: str, topic: str, transactional_id: str
) -> CommitLogWriter:
    """Create a :class:`CommitLogWriter` with idempotent producer settings."""

    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        acks="all",
        enable_idempotence=True,
        transactional_id=transactional_id,
    )
    await producer.start()
    return CommitLogWriter(producer, topic)


__all__ = ["CommitLogWriter", "create_commit_log_writer"]

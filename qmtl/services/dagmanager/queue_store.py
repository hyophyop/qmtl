from __future__ import annotations

"""Queue metadata store implementations for garbage collection."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

from .garbage_collector import QueueInfo, QueueStore
from .kafka_admin import KafkaAdmin
from .repository import NodeRepository


@dataclass
class QueueMetadata:
    """Snapshot of metadata describing a Kafka queue/topic."""

    name: str
    tag: str
    created_at: datetime
    interval: int | None = None

    def as_queue_info(self) -> QueueInfo:
        return QueueInfo(self.name, self.tag, self.created_at, interval=self.interval)


class KafkaQueueStore(QueueStore):
    """Inspect Kafka metadata and derive orphan queue candidates."""

    def __init__(
        self,
        admin: KafkaAdmin,
        repo: NodeRepository | None = None,
        *,
        default_tag: str = "indicator",
    ) -> None:
        self._admin = admin
        self._repo = repo
        self._default_tag = default_tag

    def list_orphan_queues(self) -> Iterable[QueueInfo]:
        topics = self._admin.client.list_topics()
        for name, meta in topics.items():
            if self._repo is not None:
                try:
                    if self._repo.get_node_by_queue(name) is not None:
                        continue
                except Exception:  # pragma: no cover - defensive guard
                    continue
            metadata = self._build_metadata(name, meta)
            yield metadata.as_queue_info()

    def drop_queue(self, name: str) -> None:
        self._admin.delete_topic(name)

    # ------------------------------------------------------------------
    def _build_metadata(self, name: str, meta: Mapping[str, object]) -> QueueMetadata:
        config = {}
        raw_config = meta.get("config")
        if isinstance(raw_config, Mapping):
            config = raw_config

        tag = self._extract_tag(name, config)
        created_at = self._extract_created_at(meta, config)
        interval = self._extract_interval(config)

        return QueueMetadata(name=name, tag=tag, created_at=created_at, interval=interval)

    def _extract_tag(self, name: str, config: Mapping[str, object]) -> str:
        for key in ("qmtl.tag", "qmtl_tag", "queue.tag", "queue_tag"):
            raw = config.get(key)
            if isinstance(raw, str) and raw:
                return raw

        retention = config.get("retention.ms")
        try:
            retention_ms = int(retention) if retention is not None else None
        except (TypeError, ValueError):
            retention_ms = None

        if isinstance(retention_ms, int):
            seven_days = 7 * 24 * 60 * 60 * 1000
            thirty_days = 30 * 24 * 60 * 60 * 1000
            one_eighty_days = 180 * 24 * 60 * 60 * 1000
            if retention_ms >= one_eighty_days:
                return "sentinel"
            if retention_ms <= seven_days:
                return "raw"
            if retention_ms <= thirty_days:
                return "indicator"

        lowered = name.lower()
        if "sentinel" in lowered:
            return "sentinel"

        return self._default_tag

    def _extract_created_at(
        self, meta: Mapping[str, object], config: Mapping[str, object]
    ) -> datetime:
        for source in (config, meta):
            for key in ("qmtl.created_at", "qmtl_created_at", "created_at"):
                raw = source.get(key) if isinstance(source, Mapping) else None
                if raw is None:
                    continue
                ts = self._coerce_timestamp(raw)
                if ts is not None:
                    return ts

        return datetime.now(timezone.utc)

    def _extract_interval(self, config: Mapping[str, object]) -> int | None:
        for key in ("qmtl.interval", "qmtl_interval", "interval"):
            raw = config.get(key)
            if raw is None:
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _coerce_timestamp(value: object) -> datetime | None:
        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return None
                if value.isdigit():
                    value = int(value)
                else:
                    if value.endswith("Z"):
                        value = value[:-1] + "+00:00"
                    return datetime.fromisoformat(value)
            if isinstance(value, (int, float)):
                if value > 10**12:
                    value = float(value) / 1000.0
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            if isinstance(value, datetime):
                return value.astimezone(timezone.utc)
        except Exception:  # pragma: no cover - defensive guard
            return None
        return None


__all__ = ["KafkaQueueStore", "QueueMetadata"]


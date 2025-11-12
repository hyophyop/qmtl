from __future__ import annotations

"""Utilities that expose Kafka broker metrics to the garbage collector."""

from typing import Callable
from urllib import request

from .garbage_collector import MetricsProvider


class KafkaMetricsProvider(MetricsProvider):
    """Fetch broker ingestion metrics from a Prometheus endpoint."""

    def __init__(
        self,
        endpoint: str | None,
        *,
        fetcher: Callable[[str], str] | None = None,
        timeout: float = 2.0,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._fetcher = fetcher or self._http_fetch

    def messages_in_per_sec(self) -> float:
        if not self._endpoint:
            return 0.0
        try:
            payload = self._fetcher(self._endpoint)
        except Exception:  # pragma: no cover - defensive guard
            return 0.0
        return self._parse_messages_in(payload)

    # ------------------------------------------------------------------
    def _http_fetch(self, url: str) -> str:
        with request.urlopen(url, timeout=self._timeout) as resp:
            data = resp.read()
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_messages_in(text: str) -> float:
        metric = "kafka_server_BrokerTopicMetrics_MessagesInPerSec"
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            if not line.startswith(metric):
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                return float(parts[-1])
            except (TypeError, ValueError):
                continue
        return 0.0


__all__ = ["KafkaMetricsProvider"]


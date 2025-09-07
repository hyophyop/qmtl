"""Broker adapter interfaces and simple implementations.

These adapters provide a stable surface to route standardized order payloads
to external brokers/transports. Current Runner hooks (HTTP/Kafka) remain the
primary integration; this module formalizes the shape for future expansion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from qmtl.sdk.http import HttpPoster


class BrokerAdapter(ABC):
    """Abstract broker adapter."""

    @abstractmethod
    def send(self, order: dict[str, Any]) -> None:  # pragma: no cover - interface
        """Deliver a standardized order payload to the broker."""


class HttpBrokerAdapter(BrokerAdapter):
    """HTTP adapter using SDK HttpPoster."""

    def __init__(self, url: str) -> None:
        self.url = url

    def send(self, order: dict[str, Any]) -> None:
        HttpPoster.post(self.url, json=order)


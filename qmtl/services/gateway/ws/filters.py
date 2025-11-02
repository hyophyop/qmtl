from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .connections import ConnectionFilters, RegisteredClient


@dataclass(frozen=True)
class DecodedEvent:
    """JSON payload decoded from the broadcast queue."""

    raw: str
    envelope: Mapping[str, Any] | None
    data: Mapping[str, Any] | None

    @property
    def event_id(self) -> str | None:
        if isinstance(self.envelope, Mapping):
            value = self.envelope.get("id")
            if isinstance(value, str):
                return value
        return None

    @property
    def world_id(self) -> str | None:
        if isinstance(self.data, Mapping):
            value = self.data.get("world_id")
            if isinstance(value, str):
                return value
        return None


class FilterEvaluator:
    """Decode payloads and apply connection-scoped filters."""

    def decode(self, payload: str) -> DecodedEvent:
        try:
            envelope = json.loads(payload)
        except Exception:
            return DecodedEvent(payload, None, None)
        data = envelope.get("data") if isinstance(envelope, Mapping) else None
        if isinstance(data, Mapping):
            return DecodedEvent(payload, envelope, data)
        return DecodedEvent(payload, envelope if isinstance(envelope, Mapping) else None, None)

    def filter_clients(self, clients: Sequence[RegisteredClient], event: DecodedEvent) -> list[RegisteredClient]:
        if not clients:
            return []
        world_id = event.world_id
        if world_id is None:
            return list(clients)
        allowed: list[RegisteredClient] = []
        for client in clients:
            if self._world_match(client.filters, world_id):
                allowed.append(client)
        return allowed

    @staticmethod
    def _world_match(filters: ConnectionFilters, world_id: str) -> bool:
        if filters.world_id is None:
            return True
        return filters.world_id == world_id

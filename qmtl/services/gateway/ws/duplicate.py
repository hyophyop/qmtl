from __future__ import annotations

from collections import deque
from typing import Mapping, Any


class DuplicateTracker:
    """Best-effort CloudEvent id deduplication helper."""

    def __init__(self, window: int = 10000) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self._ids: deque[str] = deque(maxlen=window)
        self._seen: set[str] = set()

    def seen(self, event: Mapping[str, Any] | None) -> bool:
        """Return ``True`` if the CloudEvent has been observed recently."""

        if not isinstance(event, Mapping):
            return False
        event_id = event.get("id")
        if not isinstance(event_id, str):
            return False
        if event_id in self._seen:
            return True
        self._ids.append(event_id)
        if len(self._ids) == self._ids.maxlen:
            self._seen = set(self._ids)
        else:
            self._seen.add(event_id)
        return False

    def clear(self) -> None:
        self._ids.clear()
        self._seen.clear()

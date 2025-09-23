from __future__ import annotations

import asyncio
from typing import Any

__all__ = ["EventRecorderService"]


class EventRecorderService:
    """Thin wrapper that persists events via the provided recorder."""

    def __init__(self, recorder: Any) -> None:
        self.recorder = recorder

    def record(self, node_id: str, interval: int, timestamp: int, payload: Any) -> None:
        if self.recorder is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                self.recorder.persist(node_id, interval, timestamp, payload)
            )
        else:  # pragma: no cover - create_task executed in loop
            loop.create_task(
                self.recorder.persist(node_id, interval, timestamp, payload)
            )

    def bind_stream(self, stream: Any) -> None:
        if self.recorder and hasattr(self.recorder, "bind_stream"):
            self.recorder.bind_stream(stream)

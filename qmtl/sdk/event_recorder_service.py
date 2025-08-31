from __future__ import annotations

"""Service wrapper for event recording."""

import asyncio
from typing import Any

from .data_io import EventRecorder


class EventRecorderService:
    """Delegate asynchronous persistence to an :class:`EventRecorder`.

    Parameters
    ----------
    recorder:
        Concrete :class:`EventRecorder` implementation. When ``None``, calls to
        :meth:`record` become no-ops.
    """

    def __init__(self, recorder: EventRecorder | None = None) -> None:
        self.recorder = recorder

    def record(self, node_id: str, interval: int, timestamp: int, payload: Any) -> None:
        """Persist ``payload`` if a recorder was configured."""
        if self.recorder is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.recorder.persist(node_id, interval, timestamp, payload))
        else:  # pragma: no cover - scheduling in running loop
            loop.create_task(self.recorder.persist(node_id, interval, timestamp, payload))


__all__ = ["EventRecorderService"]

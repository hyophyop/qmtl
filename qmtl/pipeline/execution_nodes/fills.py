"""Fill ingestion nodes."""

from __future__ import annotations

from qmtl.sdk.node import StreamInput


class FillIngestNode(StreamInput):
    """Stream node for external execution fills."""

    def __init__(self, *, name: str | None = None, interval: int | None = None) -> None:
        super().__init__(interval=interval, period=1)
        self.name = name or "fill_ingest"

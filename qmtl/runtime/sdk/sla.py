from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SLAPolicy:
    max_wait_storage_ms: int | None = None
    max_wait_backfill_ms: int | None = None
    max_wait_live_ms: int | None = None
    retry_backoff_ms: int | None = None
    total_deadline_ms: int | None = None
    max_sync_gap_bars: int | None = None


__all__ = ["SLAPolicy"]


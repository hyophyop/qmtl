from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SLAViolationMode(str, Enum):
    """Describe how Seamless should react when an SLA budget is breached."""

    FAIL_FAST = "fail_fast"
    PARTIAL_FILL = "partial_fill"
    HOLD = "hold"


@dataclass
class SLAPolicy:
    max_wait_storage_ms: int | None = None
    max_wait_backfill_ms: int | None = None
    max_wait_live_ms: int | None = None
    retry_backoff_ms: int | None = None
    total_deadline_ms: int | None = None
    max_sync_gap_bars: int | None = None
    on_violation: SLAViolationMode = SLAViolationMode.FAIL_FAST
    min_coverage: float | None = None
    max_lag_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.min_coverage is not None:
            if not 0.0 <= self.min_coverage <= 1.0:
                raise ValueError("min_coverage must be within [0.0, 1.0]")
        if self.max_lag_seconds is not None and self.max_lag_seconds < 0:
            raise ValueError("max_lag_seconds must be non-negative")


__all__ = ["SLAPolicy", "SLAViolationMode"]


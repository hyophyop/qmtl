from __future__ import annotations

"""Lightweight watermark manager for bucket readiness gating.

Stores per-topic, per-world last committed timestamps to allow nodes to gate
execution until upstream state is caught up (e.g., portfolio snapshots).
"""

from dataclasses import dataclass
from typing import Dict, Tuple

_wm: Dict[Tuple[str, str], int] = {}


@dataclass(frozen=True)
class WatermarkGate:
    """Configuration for watermark-based gating.

    Attributes
    ----------
    enabled:
        Toggle for the gate. When ``False`` the gate is bypassed.
    topic:
        State topic to consult (e.g., ``trade.portfolio``).
    lag:
        Number of full buckets that must be committed (``1`` ⇒ require ``t-1``).
    """

    enabled: bool = True
    topic: str = "trade.portfolio"
    lag: int = 1

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "topic", str(self.topic))
        lag = int(self.lag)
        if lag < 0:
            lag = 0
        object.__setattr__(self, "lag", lag)

    def required_timestamp(self, current_ts: int, interval: int | None) -> int:
        """Return the minimum watermark required for ``current_ts``.

        ``lag`` is interpreted in bucket units. When ``interval`` is not
        provided the lag is applied as a raw timestamp offset.
        """

        interval_val = int(interval or 0)
        if interval_val <= 0:
            return int(current_ts) - self.lag
        return int(current_ts) - self.lag * interval_val

    @classmethod
    def for_mode(
        cls,
        mode: str,
        *,
        topic: str = "trade.portfolio",
        lag: int = 1,
        enabled: bool | None = None,
    ) -> "WatermarkGate":
        """Create a gate with mode-aware defaults.

        ``simulate``/``backtest`` disable gating by default; ``paper`` and
        ``live`` enable it unless ``enabled`` overrides the behaviour.
        """

        normalized = (mode or "").lower()
        if enabled is None:
            enabled = normalized not in {"simulate", "backtest"}
        return cls(enabled=enabled, topic=topic, lag=lag)


def clear_watermarks() -> None:
    """Reset in-memory watermark state (primarily for tests)."""

    _wm.clear()


def set_watermark(topic: str, world_id: str, ts: int) -> None:
    key = (str(topic), str(world_id))
    cur = _wm.get(key)
    if cur is None or ts > cur:
        _wm[key] = int(ts)


def get_watermark(topic: str, world_id: str) -> int | None:
    return _wm.get((str(topic), str(world_id)))


def is_ready(topic: str, world_id: str, required_ts: int) -> bool:
    cur = get_watermark(topic, world_id)
    if cur is None:
        return False
    return int(cur) >= int(required_ts)


__all__ = [
    "WatermarkGate",
    "clear_watermarks",
    "set_watermark",
    "get_watermark",
    "is_ready",
]


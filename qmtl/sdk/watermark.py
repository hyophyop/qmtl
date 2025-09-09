from __future__ import annotations

"""Lightweight watermark manager for bucket readiness gating.

Stores per-topic, per-world last committed timestamps to allow nodes to gate
execution until upstream state is caught up (e.g., portfolio snapshots).
"""

from typing import Dict, Tuple

_wm: Dict[Tuple[str, str], int] = {}


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


__all__ = ["set_watermark", "get_watermark", "is_ready"]


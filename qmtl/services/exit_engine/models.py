"""Data models for exit engine actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitAction:
    world_id: str
    strategy_id: str
    side: str
    action: str
    reason: str
    run_id: str
    request_id: str


__all__ = ["ExitAction"]

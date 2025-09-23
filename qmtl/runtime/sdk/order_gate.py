"""Order gating utilities bridging WorldService activation and brokerage checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Activation:
    """Represents activation status per symbol or route."""

    enabled: bool
    reason: str | None = None


def gate_order(activation_map: Mapping[str, Activation], symbol: str) -> tuple[bool, str | None]:
    """Check if orders for `symbol` are allowed per activation map.

    Returns (allowed, reason).
    """
    act = activation_map.get(symbol)
    if act is None:
        return False, "activation unknown"
    if not act.enabled:
        return False, act.reason or "activation disabled"
    return True, None


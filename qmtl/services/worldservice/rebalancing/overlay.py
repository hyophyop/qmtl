from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from .base import PositionSlice, SymbolDelta
from ..schemas import OverlayConfigModel


class OverlayConfigError(ValueError):
    """Raised when overlay planning inputs are incomplete or invalid."""


@dataclass
class OverlayPlanner:
    """Compute overlay instrument deltas to adjust world-level exposure.

    Semantics
    ---------
    - Do not touch underlying positions. For each world, apply an overlay
      instrument to scale total notional by the world scaling factor.
    - For world w with scale g_w = world_after / world_before and current
      notional N_w (sum of qty * mark over positions), the overlay notional
      delta is: d_w = (g_w - 1.0) * N_w.
    - Convert to quantity using provided overlay instrument mark.

    Requirements
    ------------
    - ``overlay.instrument_by_world[world_id]`` must provide an instrument
      symbol per world.
    - ``overlay.price_by_symbol[symbol]`` must provide a mark to convert
      notional to quantity.
    """

    def plan(
        self,
        *,
        positions: List[PositionSlice],
        world_alloc_before: Mapping[str, float],
        world_alloc_after: Mapping[str, float],
        overlay: OverlayConfigModel,
        scale_by_world: Mapping[str, float] | None = None,
    ) -> List[SymbolDelta]:
        """Compute overlay deltas based on world scaling factors.

        The planner derives a per-world scale factor (either from ``scale_by_world``
        or from ``world_alloc_after/world_alloc_before``) and applies it to the
        current world notional to determine how much overlay exposure to add or
        remove. Missing configuration raises ``OverlayConfigError`` so callers can
        surface a 4xx to clients.
        """

        instruments = overlay.instrument_by_world or {}
        prices = overlay.price_by_symbol or {}
        if not instruments:
            raise OverlayConfigError("overlay.instrument_by_world is required for overlay mode")
        if not prices:
            raise OverlayConfigError("overlay.price_by_symbol is required for overlay mode")

        world_notional: Dict[str, float] = {}
        for pos in positions:
            world_notional[pos.world_id] = world_notional.get(pos.world_id, 0.0) + pos.notional

        deltas: List[SymbolDelta] = []
        min_notional = overlay.min_order_notional or 0.0

        for world_id, alloc_after in world_alloc_after.items():
            instrument = instruments.get(world_id)
            if instrument is None:
                raise OverlayConfigError(f"overlay.instrument_by_world missing world '{world_id}'")
            price = prices.get(instrument)
            if price is None or price == 0:
                raise OverlayConfigError(
                    f"overlay.price_by_symbol missing or zero for instrument '{instrument}'"
                )

            notional = world_notional.get(world_id, 0.0)
            if notional == 0:
                continue

            scale_world = None
            if scale_by_world is not None:
                scale_world = scale_by_world.get(world_id)
            if scale_world is None:
                alloc_before = world_alloc_before.get(world_id, 0.0)
                if alloc_before <= 0:
                    continue
                scale_world = alloc_after / alloc_before

            delta_notional = (scale_world - 1.0) * notional
            if abs(delta_notional) < min_notional:
                continue

            deltas.append(
                SymbolDelta(
                    symbol=instrument,
                    delta_qty=delta_notional / price,
                    venue=None,
                )
            )

        return deltas


__all__ = ["OverlayPlanner", "OverlayConfigError"]

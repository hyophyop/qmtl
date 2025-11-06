from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

from .base import PositionSlice, SymbolDelta
from ..schemas import OverlayConfigModel


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
    ) -> List[SymbolDelta]:
        instrument_by_world = (overlay.instrument_by_world or {})
        price_by_symbol = (overlay.price_by_symbol or {})
        min_notional = float(getattr(overlay, "min_order_notional", 0.0) or 0.0)

        # Aggregate world notionals
        world_notional: Dict[str, float] = {}
        for p in positions:
            world_notional[p.world_id] = world_notional.get(p.world_id, 0.0) + (p.qty * p.mark)

        deltas: List[SymbolDelta] = []
        for wid, n in world_notional.items():
            before = float(world_alloc_before.get(wid, 0.0))
            after = float(world_alloc_after.get(wid, 0.0))
            if before <= 0.0:
                # If there was no prior allocation, overlay cannot infer scaling relative to existing exposure
                continue
            g = after / before
            d_notional = (g - 1.0) * n
            if abs(d_notional) < min_notional:
                continue
            inst = instrument_by_world.get(wid)
            if not inst:
                continue
            mark = float(price_by_symbol.get(inst, 0.0))
            if mark <= 0.0:
                continue
            qty = d_notional / mark
            if qty == 0.0:
                continue
            deltas.append(SymbolDelta(symbol=inst, delta_qty=qty, venue=None))
        return deltas


__all__ = ["OverlayPlanner"]


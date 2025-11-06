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
        raise NotImplementedError(
            "Overlay mode is not implemented. This requires further design discussions (proxy instrument mapping, risk/constraints)."
        )


__all__ = ["OverlayPlanner"]

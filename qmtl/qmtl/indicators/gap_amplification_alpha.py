"""Gap amplification indicator node."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

from __future__ import annotations

from typing import Sequence, Tuple, Dict

from qmtl.transforms.gap_amplification import (
    gap_over_depth_sum,
    gati_side,
    hazard_probability,
    jump_expectation,
)


def gap_amplification_node(
    ask_gaps: Sequence[float],
    ask_depths: Sequence[float],
    bid_gaps: Sequence[float],
    bid_depths: Sequence[float],
    lam: float,
    ofi: float,
    spread_z: float,
    eta: Tuple[float, float, float],
    zeta: float = 0.0,
) -> Dict[str, float]:
    """Compute gap amplification transition alpha."""
    gas_ask = gap_over_depth_sum(ask_gaps, ask_depths, lam)
    gas_bid = gap_over_depth_sum(bid_gaps, bid_depths, lam)
    hazard = hazard_probability(ofi, spread_z, *eta)
    jump_ask = jump_expectation(ask_gaps, ask_depths, zeta)
    jump_bid = jump_expectation(bid_gaps, bid_depths, zeta)
    gati_ask = gati_side(gas_ask, hazard, jump_ask)
    gati_bid = gati_side(gas_bid, hazard, jump_bid)
    return {
        "gas_ask": gas_ask,
        "gas_bid": gas_bid,
        "hazard": hazard,
        "jump_ask": jump_ask,
        "jump_bid": jump_bid,
        "gati_ask": gati_ask,
        "gati_bid": gati_bid,
        "alpha": gati_bid - gati_ask,
    }

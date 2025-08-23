"""Gap amplification indicator with hazard-based alpha."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "gap_amplification",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.gap_amplification import (
    gap_over_depth_sum,
    gati_side,
    hazard_probability,
)
from qmtl.sdk.cache_view import CacheView

from strategies.utils.cacheview_helpers import level_series, value_at


def _gas(gaps: list[float], depths: list[float], lam: float) -> float:
    """Wrapper for gap amplification score."""
    return gap_over_depth_sum(gaps, depths, lam)


def _hazard(
    ofi: float, spread_z: float, eta0: float, eta1: float, eta2: float
) -> float:
    """Wrapper for hazard probability."""
    return hazard_probability(ofi, spread_z, eta0, eta1, eta2)


def gap_amplification_node(data: dict, view: CacheView | None = None) -> dict:
    """Compute gap amplification transition alpha.

    Parameters
    ----------
    data:
        Mapping containing either precomputed values or raw inputs:
            ``gas_ask``, ``gas_bid`` and ``hazard``
                Precomputed gap amplification and hazard metrics.
            ``ask_gaps``, ``ask_depths``, ``bid_gaps``, ``bid_depths``, ``lambda``
                Raw inputs for computing ``gas_*`` when precomputed values absent.
            ``ofi``, ``spread_z``, ``eta``
                Raw inputs for computing ``hazard`` when absent.
            ``time``
                Index used when fetching cached inputs.

    view:
        Optional :class:`~qmtl.sdk.cache_view.CacheView` supplying cached data.

    Returns
    -------
    dict
        Mapping with ``gati_ask``, ``gati_bid`` and directional ``alpha``.
    """

    gas_ask = data.get("gas_ask")
    gas_bid = data.get("gas_bid")
    hazard = data.get("hazard")

    ask_gaps = data.get("ask_gaps")
    ask_depths = data.get("ask_depths")
    bid_gaps = data.get("bid_gaps")
    bid_depths = data.get("bid_depths")
    ofi = data.get("ofi")
    spread_z = data.get("spread_z")
    eta = data.get("eta")

    lam = data.get("lambda", 0.0)
    time_idx = data.get("time", 0)

    if view is not None:
        try:
            if ask_gaps is None:
                ask_gaps = level_series(view, time_idx, "ask", "gap")
            if ask_depths is None:
                ask_depths = level_series(view, time_idx, "ask", "depth")
            if bid_gaps is None:
                bid_gaps = level_series(view, time_idx, "bid", "gap")
            if bid_depths is None:
                bid_depths = level_series(view, time_idx, "bid", "depth")
            if hazard is None:
                ofi = value_at(view, time_idx, "hazard", 0, "ofi", ofi)
                spread_z = value_at(view, time_idx, "hazard", 0, "spread_z", spread_z)
                if eta is None:
                    eta0 = value_at(view, time_idx, "hazard", 0, "eta0")
                    eta1 = value_at(view, time_idx, "hazard", 0, "eta1")
                    eta2 = value_at(view, time_idx, "hazard", 0, "eta2")
                    if None not in (eta0, eta1, eta2):
                        eta = (eta0, eta1, eta2)
        except Exception:  # pragma: no cover - defensive
            pass

    if gas_ask is None and ask_gaps is not None and ask_depths is not None:
        gas_ask = _gas(ask_gaps, ask_depths, lam)
    if gas_bid is None and bid_gaps is not None and bid_depths is not None:
        gas_bid = _gas(bid_gaps, bid_depths, lam)

    if hazard is None and ofi is not None and spread_z is not None and eta is not None and None not in eta:
        hazard = _hazard(ofi, spread_z, *eta)

    gas_ask = gas_ask or 0.0
    gas_bid = gas_bid or 0.0
    hazard = hazard or 0.0

    gati_ask = gati_side(gas_ask, hazard)
    gati_bid = gati_side(gas_bid, hazard)
    alpha = gati_bid - gati_ask

    if view is not None:
        cache_time = view._data.setdefault(time_idx, {})
        ask_cache = cache_time.setdefault("ask", {}).setdefault(0, {})
        bid_cache = cache_time.setdefault("bid", {}).setdefault(0, {})
        haz_cache = cache_time.setdefault("hazard", {}).setdefault(0, {})
        ask_cache["gas"] = gas_ask
        ask_cache["gati"] = gati_ask
        bid_cache["gas"] = gas_bid
        bid_cache["gati"] = gati_bid
        haz_cache["hazard"] = hazard

    return {
        "gas_ask": gas_ask,
        "gas_bid": gas_bid,
        "gati_ask": gati_ask,
        "gati_bid": gati_bid,
        "hazard": hazard,
        "alpha": alpha,
    }


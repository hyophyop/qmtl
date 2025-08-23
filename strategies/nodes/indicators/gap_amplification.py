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
        cache = view._data  # underlying mapping for mutation and iteration
        try:
            if ask_gaps is None or ask_depths is None:
                ask_levels = cache[time_idx]["ask"]
                gaps: list[float] = []
                depths: list[float] = []
                for lvl in sorted(ask_levels):
                    feats = ask_levels[lvl]
                    if "gap" in feats and "depth" in feats:
                        gaps.append(feats["gap"])
                        depths.append(feats["depth"])
                if ask_gaps is None:
                    ask_gaps = gaps
                if ask_depths is None:
                    ask_depths = depths
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            if bid_gaps is None or bid_depths is None:
                bid_levels = cache[time_idx]["bid"]
                gaps = []
                depths = []
                for lvl in sorted(bid_levels):
                    feats = bid_levels[lvl]
                    if "gap" in feats and "depth" in feats:
                        gaps.append(feats["gap"])
                        depths.append(feats["depth"])
                if bid_gaps is None:
                    bid_gaps = gaps
                if bid_depths is None:
                    bid_depths = depths
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            if hazard is None:
                haz_feats = cache[time_idx]["hazard"][0]
                ofi = haz_feats.get("ofi", ofi)
                spread_z = haz_feats.get("spread_z", spread_z)
                if eta is None:
                    eta = (
                        haz_feats.get("eta0"),
                        haz_feats.get("eta1"),
                        haz_feats.get("eta2"),
                    )
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


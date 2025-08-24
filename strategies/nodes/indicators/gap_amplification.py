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
    jump_expectation,
    filter_ghost_quotes,
)
from qmtl.sdk.cache_view import CacheView

from strategies.utils.cacheview_helpers import level_series, value_at


def _gas(gaps: list[float], depths: list[float], lam: float) -> float:
    """Wrapper for gap amplification score."""
    return gap_over_depth_sum(gaps, depths, lam)


def _hazard(
    ofi: float,
    spread_z: float,
    vol_surprise: float,
    clr: float,
    eta0: float,
    eta1: float,
    eta2: float,
    eta3: float,
    eta4: float,
) -> float:
    """Wrapper for hazard probability."""
    return hazard_probability(
        ofi,
        spread_z,
        eta0,
        eta1,
        eta2,
        vol_surprise,
        clr,
        eta3,
        eta4,
    )


def _jump(
    gaps: list[float],
    depths: list[float],
    zeta: float,
    microprice_slope: float,
) -> float:
    """Wrapper for jump expectation."""
    return jump_expectation(gaps, depths, zeta, microprice_slope)


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
    jump_ask = data.get("jump_ask")
    jump_bid = data.get("jump_bid")

    ask_gaps = data.get("ask_gaps")
    ask_depths = data.get("ask_depths")
    bid_gaps = data.get("bid_gaps")
    bid_depths = data.get("bid_depths")
    ask_dwell = data.get("ask_dwell")
    bid_dwell = data.get("bid_dwell")
    tau_min = data.get("tau_min")
    ofi = data.get("ofi")
    spread_z = data.get("spread_z")
    vol_surprise = data.get("vol_surprise")
    cancel_limit_ratio = data.get("cancel_limit_ratio")
    eta = data.get("eta")
    zeta = data.get("zeta", 0.0)
    microprice_slope = data.get("microprice_slope", 0.0)

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
                vol_surprise = value_at(
                    view, time_idx, "hazard", 0, "vol_surprise", vol_surprise
                )
                cancel_limit_ratio = value_at(
                    view, time_idx, "hazard", 0, "cancel_limit_ratio", cancel_limit_ratio
                )
                if eta is None:
                    eta0 = value_at(view, time_idx, "hazard", 0, "eta0")
                    eta1 = value_at(view, time_idx, "hazard", 0, "eta1")
                    eta2 = value_at(view, time_idx, "hazard", 0, "eta2")
                    eta3 = value_at(view, time_idx, "hazard", 0, "eta3")
                    eta4 = value_at(view, time_idx, "hazard", 0, "eta4")
                    if None not in (eta0, eta1, eta2, eta3, eta4):
                        eta = (eta0, eta1, eta2, eta3, eta4)
        except Exception:  # pragma: no cover - defensive
            pass

    if (
        tau_min is not None
        and ask_gaps is not None
        and ask_depths is not None
        and ask_dwell is not None
    ):
        ask_gaps, ask_depths = filter_ghost_quotes(ask_gaps, ask_depths, ask_dwell, tau_min)
    if (
        tau_min is not None
        and bid_gaps is not None
        and bid_depths is not None
        and bid_dwell is not None
    ):
        bid_gaps, bid_depths = filter_ghost_quotes(bid_gaps, bid_depths, bid_dwell, tau_min)

    if gas_ask is None and ask_gaps is not None and ask_depths is not None:
        gas_ask = _gas(ask_gaps, ask_depths, lam)
    if gas_bid is None and bid_gaps is not None and bid_depths is not None:
        gas_bid = _gas(bid_gaps, bid_depths, lam)

    if jump_ask is None and ask_gaps is not None and ask_depths is not None:
        jump_ask = _jump(ask_gaps, ask_depths, zeta, microprice_slope)
    if jump_bid is None and bid_gaps is not None and bid_depths is not None:
        jump_bid = _jump(bid_gaps, bid_depths, zeta, microprice_slope)

    if (
        hazard is None
        and ofi is not None
        and spread_z is not None
        and vol_surprise is not None
        and cancel_limit_ratio is not None
        and eta is not None
        and len(eta) == 5
        and None not in eta
    ):
        hazard = _hazard(
            ofi,
            spread_z,
            vol_surprise,
            cancel_limit_ratio,
            *eta,
        )

    gas_ask = gas_ask or 0.0
    gas_bid = gas_bid or 0.0
    hazard = hazard or 0.0
    jump_ask = jump_ask or 1.0
    jump_bid = jump_bid or 1.0

    gati_ask = gati_side(gas_ask, hazard, jump_ask)
    gati_bid = gati_side(gas_bid, hazard, jump_bid)
    alpha = gati_bid - gati_ask

    if view is not None:
        cache_time = view._data.setdefault(time_idx, {})
        ask_cache = cache_time.setdefault("ask", {}).setdefault(0, {})
        bid_cache = cache_time.setdefault("bid", {}).setdefault(0, {})
        haz_cache = cache_time.setdefault("hazard", {}).setdefault(0, {})
        ask_cache["gas"] = gas_ask
        ask_cache["gati"] = gati_ask
        ask_cache["jump"] = jump_ask
        bid_cache["gas"] = gas_bid
        bid_cache["gati"] = gati_bid
        bid_cache["jump"] = jump_bid
        haz_cache["hazard"] = hazard
        haz_cache["ofi"] = ofi
        haz_cache["spread_z"] = spread_z
        haz_cache["vol_surprise"] = vol_surprise
        haz_cache["cancel_limit_ratio"] = cancel_limit_ratio
        if eta is not None and len(eta) == 5:
            haz_cache["eta0"], haz_cache["eta1"], haz_cache["eta2"], haz_cache["eta3"], haz_cache["eta4"] = eta

    return {
        "gas_ask": gas_ask,
        "gas_bid": gas_bid,
        "gati_ask": gati_ask,
        "gati_bid": gati_bid,
        "hazard": hazard,
        "jump_ask": jump_ask,
        "jump_bid": jump_bid,
        "alpha": alpha,
    }


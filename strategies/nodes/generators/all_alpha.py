from __future__ import annotations

"""Feature generator consolidating data for multiple alpha modules.

The generator wraps :class:`qmtl.generators.raw_market.RawMarketInput` and
produces a dictionary with the following top-level keys expected by downstream
alpha indicators:

``apb``
    ``price``, ``volume``, ``volume_hat``, ``volume_std``
``llrti``
    ``depth_changes``, ``price_change``, ``delta_t``, ``delta``
``non_linear``
    ``impact``, ``volatility``, ``obi_derivative``
``order_book``
    ``hazard_ask``, ``hazard_bid``, ``g_ask``, ``g_bid``, ``pi``, ``cost``
``qle``
    ``alphas``, ``delta_t``, ``tau``, ``sigma``, ``threshold``
``resiliency``
    ``volume``, ``avg_volume``, ``depth``, ``volatility``, ``obi_derivative``,
    ``beta``, ``gamma``

History is maintained internally so that moving statistics are calculated over
recent observations without leaking unbounded memory.
"""

from statistics import stdev
from typing import Sequence

from qmtl.generators.raw_market import RawMarketInput
from qmtl.transforms import (
    volume_stats,
    order_book_imbalance,
    execution_imbalance,
    rate_of_change_series,
    price_delta,
    hazard_probability,
    direction_gating,
    execution_cost,
    llrti,
)
from qmtl.transforms.quantum_liquidity_echo import quantum_liquidity_echo

TAGS = {
    "scope": "generator",
    "family": "all_alpha",
    "interval": "1s",
    "asset": "sample",
}

_raw = RawMarketInput(interval=1, period=1, seed=0)
_history = {
    "volume": [],
    "obi": [],
    "exec": [],
    "price": [],
    "depth_changes": [],
    "llrti": [],
}


def _append(key: str, value: float, window: int = 5) -> None:
    hist = _history[key]
    hist.append(value)
    if len(hist) > window:
        del hist[0]


def _volatility(values: Sequence[float]) -> float:
    """Return standard deviation of percentage returns for ``values``."""
    if len(values) < 2:
        return 0.0
    returns = [(values[i] / values[i - 1]) - 1 for i in range(1, len(values))]
    if len(returns) < 2:
        return 0.0
    return stdev(returns)


def all_alpha_generator_node() -> dict:
    """Return feature dictionary for composite alpha modules."""
    _, raw = _raw.step()
    price = raw["price"]
    volume = raw["volume"]
    _append("volume", volume)
    volume_hat, volume_std = volume_stats(_history["volume"])

    bid_vol = raw["bid_volume"]
    ask_vol = raw["ask_volume"]
    obi = order_book_imbalance(bid_vol, ask_vol)
    _append("obi", obi, window=2)
    obi_deriv = rate_of_change_series(_history["obi"])
    depth = bid_vol + ask_vol

    buy = raw["buy_volume"]
    sell = raw["sell_volume"]
    exec_imb = execution_imbalance(buy, sell)
    _append("exec", exec_imb, window=2)
    exec_deriv = rate_of_change_series(_history["exec"])

    _append("price", price, window=2)
    price_change = 0.0
    if len(_history["price"]) >= 2:
        price_change = price_delta(_history["price"][-2], _history["price"][-1])
    _append("depth_changes", raw["depth_change"], window=3)
    llrti_val = llrti(_history["depth_changes"], price_change, 1.0, 0.01)
    _append("llrti", llrti_val, window=3)

    vol = _volatility(_history["price"])

    hazard_ask = hazard_probability(
        {
            "C": raw["ask_z_C"],
            "Cliff": raw["ask_z_Cliff"],
            "Gap": raw["ask_z_Gap"],
            "CH": raw["ask_z_CH"],
            "RL": raw["ask_z_RL"],
            "Shield": raw["ask_z_Shield"],
            "QDT_inv": raw["ask_z_QDT_inv"],
            "Pers": raw["ask_z_Pers"],
        },
        (0.0,) * 9,
    )
    hazard_bid = hazard_probability(
        {
            "C": raw["bid_z_C"],
            "Cliff": raw["bid_z_Cliff"],
            "Gap": raw["bid_z_Gap"],
            "CH": raw["bid_z_CH"],
            "RL": raw["bid_z_RL"],
            "Shield": raw["bid_z_Shield"],
            "QDT_inv": raw["bid_z_QDT_inv"],
            "Pers": raw["bid_z_Pers"],
        },
        (0.0,) * 9,
    )
    g_ask = direction_gating(
        +1,
        {
            "OFI": raw["ask_z_OFI"],
            "MicroSlope": raw["ask_z_MicroSlope"],
            "AggFlow": raw["ask_z_AggFlow"],
        },
        (0.0,) * 4,
    )
    g_bid = direction_gating(
        -1,
        {
            "OFI": raw["bid_z_OFI"],
            "MicroSlope": raw["bid_z_MicroSlope"],
            "AggFlow": raw["bid_z_AggFlow"],
        },
        (0.0,) * 4,
    )
    cost = execution_cost(raw["spread"], raw["taker_fee"], raw["impact"])

    echo, qe, action = quantum_liquidity_echo(_history["llrti"], 1.0, 1.0, 0.1, 0.0)

    return {
        "apb": {
            "price": price,
            "volume": volume,
            "volume_hat": volume_hat,
            "volume_std": volume_std,
        },
        "llrti": {
            "depth_changes": list(_history["depth_changes"]),
            "price_change": price_change,
            "delta_t": 1.0,
            "delta": 0.01,
        },
        "non_linear": {
            "impact": raw["impact"],
            "volatility": vol,
            "obi_derivative": obi_deriv,
        },
        "order_book": {
            "hazard_ask": hazard_ask,
            "hazard_bid": hazard_bid,
            "g_ask": g_ask,
            "g_bid": g_bid,
            "pi": 1.0,
            "cost": cost,
        },
        "qle": {
            "alphas": list(_history["llrti"]),
            "delta_t": 1.0,
            "tau": 1.0,
            "sigma": 0.1,
            "threshold": 0.0,
        },
        "resiliency": {
            "volume": volume,
            "avg_volume": volume_hat,
            "depth": depth,
            "volatility": vol,
            "obi_derivative": obi_deriv,
            "beta": 1.0,
            "gamma": 1.0,
        },
    }


__all__ = ["all_alpha_generator_node"]

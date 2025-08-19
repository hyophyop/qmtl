"""Generate features for all alpha indicators from raw market data."""

TAGS = {
    "scope": "generator",
    "family": "all_alpha",
    "interval": "1s",
    "asset": "sample",
}

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
from qmtl.indicators import volatility
from qmtl.transforms.quantum_liquidity_echo import quantum_liquidity_echo

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


def all_alpha_generator_node() -> dict:
    """Return feature dictionary for composite alpha."""
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

    vol = volatility(_history["price"])

    hazard_ask = hazard_probability(
        {
            "C": raw["ask_z_C"],
            "Cliff": raw["ask_z_Cliff"],
            "Gap": raw["ask_z_Gap"],
            "CH": raw["ask_z_CH"],
            "RL": raw["ask_z_RL"],
            "Shield": raw["ask_z_Shield"],
            "QDT_inv": raw["ask_z_QDT_inv"],
        },
        (0.0,) * 8,
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
        },
        (0.0,) * 8,
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
    }

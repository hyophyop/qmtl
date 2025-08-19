"""Composite alpha combining all implemented alpha signals."""

from __future__ import annotations

TAGS = {
    "scope": "indicator",
    "family": "composite_alpha",
    "interval": "1d",
    "asset": "sample",
}

from .acceptable_price_band import acceptable_price_band_node
from .llrti import llrti_node
from .latent_liquidity_alpha import latent_liquidity_alpha_node
from .non_linear_alpha import non_linear_alpha_node
from .order_book_clustering_collapse import (
    order_book_clustering_collapse_node,
)
from .quantum_liquidity_echo import quantum_liquidity_echo_node


def composite_alpha_node(data: dict) -> dict:
    """Compute mean alpha across all available signals."""
    apb = acceptable_price_band_node(data.get("apb", {}))
    llrti_val = llrti_node(data.get("llrti", {})).get("llrti", 0.0)
    lla = latent_liquidity_alpha_node({"llrti": llrti_val})
    nla = non_linear_alpha_node(data.get("non_linear", {}))
    occ = order_book_clustering_collapse_node(data.get("order_book", {}))
    qle = quantum_liquidity_echo_node(data.get("qle", {}))
    components = [
        apb.get("alpha", 0.0),
        lla.get("alpha", 0.0),
        nla.get("alpha", 0.0),
        occ.get("alpha", 0.0),
        qle.get("echo_amplitude", 0.0),
    ]
    alpha = sum(components) / len(components) if components else 0.0
    return {
        "alpha": alpha,
        "components": {
            "acceptable_price_band": components[0],
            "latent_liquidity": components[1],
            "non_linear": components[2],
            "order_book_clustering": components[3],
            "quantum_echo": components[4],
        },
    }

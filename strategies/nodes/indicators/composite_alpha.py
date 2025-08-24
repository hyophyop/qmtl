"""Composite alpha combining all implemented alpha signals."""

from __future__ import annotations

TAGS = {
    "scope": "indicator",
    "family": "composite_alpha",
    "interval": "1d",
    "asset": "sample",
}

from .acceptable_price_band import acceptable_price_band_node
from .gap_amplification import gap_amplification_node
from .llrti import llrti_node
from .latent_liquidity_alpha import latent_liquidity_alpha_node
from .non_linear_alpha import non_linear_alpha_node
from .order_book_clustering_collapse import (
    order_book_clustering_collapse_node,
)
from .quantum_liquidity_echo import quantum_liquidity_echo_node
from .tactical_liquidity_bifurcation import tactical_liquidity_bifurcation_node
from .execution_diffusion_contraction import execution_diffusion_contraction_node
from .resiliency_alpha import resiliency_alpha_node
from .execution_velocity_hazard import execution_velocity_hazard_node


def composite_alpha_node(data: dict) -> dict:
    """Compute mean alpha across all available signals."""
    apb = acceptable_price_band_node(data.get("apb", {}))
    gap_amp = gap_amplification_node(data.get("gap_amplification", {}))
    llrti_res = llrti_node(data.get("llrti", {}))
    llrti_val = llrti_res.get("llrti", 0.0)
    hazard = llrti_res.get("hazard", 0.0)
    cost = llrti_res.get("cost", 0.0)
    lla = latent_liquidity_alpha_node({"llrti": llrti_val, "hazard": hazard, "cost": cost})
    nla = non_linear_alpha_node(data.get("non_linear", {}))
    occ = order_book_clustering_collapse_node(data.get("order_book", {}))
    qle = quantum_liquidity_echo_node(data.get("qle", {}))
    tlb = tactical_liquidity_bifurcation_node(data.get("tactical_liquidity", {}))
    edch = execution_diffusion_contraction_node(data.get("edch", {}))
    resil = resiliency_alpha_node(data.get("resiliency", {}))
    evh = execution_velocity_hazard_node(data.get("edvh", {}))

    components = [
        apb.get("alpha", 0.0),
        gap_amp.get("alpha", 0.0),
        lla.get("alpha", 0.0),
        nla.get("alpha", 0.0),
        occ.get("alpha", 0.0),
        qle.get("echo_amplitude", 0.0),
        tlb.get("alpha", 0.0),
        edch.get("alpha", 0.0),
        resil.get("alpha", 0.0),
        evh.get("alpha", 0.0),
    ]
    alpha = sum(components) / len(components) if components else 0.0
    return {
        "alpha": alpha,
        "components": {
            "acceptable_price_band": components[0],
            "gap_amplification": components[1],
            "latent_liquidity": components[2],
            "non_linear": components[3],
            "order_book_clustering": components[4],
            "quantum_echo": components[5],
            "tactical_liquidity_bifurcation": components[6],
            "execution_diffusion_contraction": components[7],
            "resiliency": components[8],
            "execution_velocity_hazard": components[9],
        },
    }

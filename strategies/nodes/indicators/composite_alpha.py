"""Composite alpha combining all implemented alpha signals."""

from __future__ import annotations

from collections.abc import Mapping

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


def composite_alpha_node(
    data: dict, weights: Mapping[str, float] | None = None
) -> dict:
    """Compute weighted mean alpha across all available signals."""
    apb = acceptable_price_band_node(data.get("apb", {}))
    gap_amp = gap_amplification_node(data.get("gap_amplification", {}))
    llrti_res = llrti_node(data.get("llrti", {}))
    llrti_val = llrti_res.get("llrti", 0.0)
    hazard_jump = llrti_res.get("hazard_jump", 0.0)
    cost = llrti_res.get("cost", 0.0)
    lla = latent_liquidity_alpha_node(
        {"llrti": llrti_val, "hazard_jump": hazard_jump, "cost": cost}
    )
    nla = non_linear_alpha_node(data.get("non_linear", {}))
    occ = order_book_clustering_collapse_node(data.get("order_book", {}))
    qle = quantum_liquidity_echo_node(data.get("qle", {}))
    tlb = tactical_liquidity_bifurcation_node(data.get("tactical_liquidity", {}))
    edch = execution_diffusion_contraction_node(data.get("edch", {}))
    resil = resiliency_alpha_node(data.get("resiliency", {}))
    evh = execution_velocity_hazard_node(data.get("edvh", {}))

    components = {
        "acceptable_price_band": apb.get("alpha", 0.0),
        "gap_amplification": gap_amp.get("alpha", 0.0),
        "latent_liquidity": lla.get("alpha", 0.0),
        "non_linear": nla.get("alpha", 0.0),
        "order_book_clustering": occ.get("alpha", 0.0),
        "quantum_echo": qle.get("echo_amplitude", 0.0),
        "tactical_liquidity_bifurcation": tlb.get("alpha", 0.0),
        "execution_diffusion_contraction": edch.get("alpha", 0.0),
        "resiliency": resil.get("alpha", 0.0),
        "execution_velocity_hazard": evh.get("alpha", 0.0),
    }
    weight_map = {**{k: 1.0 for k in components}, **(weights or {})}
    total_weight = sum(weight_map[k] for k in components)
    alpha = (
        sum(components[k] * weight_map[k] for k in components) / total_weight
        if components
        else 0.0
    )
    return {"alpha": alpha, "components": components}

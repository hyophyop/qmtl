"""Execution diffusion–contraction hazard indicator."""

# Source: docs/alphadocs/ideas/gpt5pro/Dynamic Execution Diffusion-Contraction Theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "execution_diffusion_contraction",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.execution_diffusion_contraction import (
    hazard_probability,
    expected_jump,
    edch_side,
)


def _edch(data: dict, side: str) -> float:
    prob_key = f"{side}_prob"
    jump_key = f"{side}_jump"
    prob = data.get(prob_key)
    jump = data.get(jump_key)
    if prob is None and f"{side}_inputs" in data and f"{side}_eta" in data:
        prob = hazard_probability(data[f"{side}_inputs"], data[f"{side}_eta"])
    if jump is None and {f"{side}_gaps", f"{side}_cum_depth", f"{side}_Q"}.issubset(data):
        jump = expected_jump(
            data[f"{side}_gaps"],
            data[f"{side}_cum_depth"],
            data[f"{side}_Q"],
        )
    prob = prob or 0.0
    jump = jump or 0.0
    return edch_side(prob, jump)


def execution_diffusion_contraction_node(data: dict) -> dict:
    """Compute execution diffusion–contraction hazard alpha."""
    edch_up = data.get("edch_up")
    edch_down = data.get("edch_down")

    if edch_up is None:
        edch_up = _edch(data, "up")
    if edch_down is None:
        edch_down = _edch(data, "down")

    alpha = edch_up - edch_down
    return {
        "edch_up": edch_up,
        "edch_down": edch_down,
        "alpha": alpha,
    }

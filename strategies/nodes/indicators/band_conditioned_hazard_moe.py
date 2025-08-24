"""Band-conditioned hazard mixture-of-experts indicator.

# Source: docs/alphadocs/ideas/gpt5pro/Band-conditioned Hazard Mixture-of-Experts(original).md
# Priority: gpt5pro
"""

from __future__ import annotations

import math

TAGS = {
    "scope": "indicator",
    "family": "band_conditioned_hazard_moe",
    "interval": "1d",
    "asset": "sample",
}


def _softsign(x: float) -> float:
    """Compute softsign activation."""
    return x / (1.0 + abs(x))


def band_conditioned_hazard_moe_node(data: dict) -> dict:
    """Compute band-conditioned hazard mixture-of-experts alpha.

    Parameters
    ----------
    data:
        Mapping of inputs. Expected keys include ``pbx``, ``hazard_up``,
        ``hazard_down``, ``spread_z``, ``overshoot``, ``compression``, and
        ``intensity_grad``. Optional parameter tuples:

        ``beta``: ``(beta1, beta2)`` scaling for momentum expert.
        ``gamma``: ``(gamma1, gamma2)`` scaling for reversion expert.
        ``omega``: ``(omega0, omega1, omega2, omega3)`` gating weights.
        ``theta_band``: band threshold for activating momentum expert.
        ``theta_in``: inner threshold for reversion expert.
        ``kappa``: spread penalty for momentum expert.

    Returns
    -------
    dict
        Dictionary with ``alpha`` and intermediate components.
    """

    pbx = data.get("pbx", 0.0)
    hazard_up = data.get("hazard_up", 0.0)
    hazard_down = data.get("hazard_down", 0.0)
    spread_z = data.get("spread_z", 0.0)
    overshoot = data.get("overshoot", 0.0)
    compression = data.get("compression", 0.0)
    intensity_grad = data.get("intensity_grad", 0.0)

    theta_band = data.get("theta_band", 1.0)
    theta_in = data.get("theta_in", theta_band)
    beta1, beta2 = data.get("beta", (1.0, 1.0))
    gamma1, gamma2 = data.get("gamma", (1.0, 1.0))
    omega0, omega1, omega2, omega3 = data.get("omega", (0.0, 1.0, 1.0, 1.0))
    kappa = data.get("kappa", 0.0)

    momentum_active = abs(pbx) > theta_band
    diff = hazard_up - hazard_down
    alpha_mom = (
        beta1 * _softsign(beta2 * diff) * math.exp(-kappa * spread_z)
        if momentum_active
        else 0.0
    )

    rev_active = abs(pbx) < theta_in
    inner = gamma2 * (theta_in - abs(pbx))
    alpha_rev = -gamma1 * math.log1p(math.exp(inner)) if rev_active else 0.0

    gate_arg = (
        omega0 + omega1 * overshoot + omega2 * compression + omega3 * intensity_grad
    )
    gate = 1.0 / (1.0 + math.exp(-gate_arg))

    alpha = gate * alpha_mom + (1.0 - gate) * alpha_rev

    return {
        "alpha": alpha,
        "gate": gate,
        "alpha_mom": alpha_mom,
        "alpha_rev": alpha_rev,
    }

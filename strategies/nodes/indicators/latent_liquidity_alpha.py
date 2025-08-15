"""Latent liquidity non-linear alpha."""

# Source: docs/alphadocs/latent-liquidity-threshold-reconfiguration.md

TAGS = {
    "scope": "signal",
    "family": "alpha",
    "interval": "1d",
    "asset": "sample",
}

import math


def latent_liquidity_alpha_node(data: dict) -> dict:
    """Compute alpha from LLRTI and execution imbalance dynamics.

    Parameters
    ----------
    data:
        Mapping with ``llrti`` value, ``gamma`` exponent, ``theta1`` and ``theta2``
        coefficients, and ``exec_imbalance_deriv`` derivative term.

    Returns
    -------
    dict
        Mapping with ``"alpha"`` key for the computed signal.
    """

    llrti = data.get("llrti", 0.0)
    gamma = data.get("gamma", 1.0)
    theta1 = data.get("theta1", 1.0)
    theta2 = data.get("theta2", 1.0)
    exec_deriv = data.get("exec_imbalance_deriv", 0.0)

    alpha = theta1 * math.log(1 + abs(llrti) ** gamma) + theta2 * exec_deriv
    return {"alpha": alpha}

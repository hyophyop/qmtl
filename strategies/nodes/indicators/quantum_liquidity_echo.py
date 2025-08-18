"""Quantum Liquidity Echo indicator module."""

# Source: docs/alphadocs/ideas/gpt5pro/quantum-liquidity-echo-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "quantum_liquidity_echo",
    "interval": "1d",
    "asset": "sample",
}

import math
from typing import Iterable


def quantum_liquidity_echo_node(data: dict) -> dict:
    """Estimate echo amplitude and amplification index with threshold logic.

    Parameters
    ----------
    data:
        Mapping with ``alphas`` sequence, decay ``delta_t`` spacing, decay constant
        ``tau``, instantaneous volatility ``sigma`` and triggering ``threshold``.

    Returns
    -------
    dict
        Mapping with ``"echo_amplitude"``, ``"qe"`` (amplification index) and
        ``"action"`` fields. ``action`` is ``-1`` or ``1`` when the amplification
        index exceeds ``threshold`` (sign is opposite ``echo_amplitude``) otherwise
        ``0``.
    """

    alphas: Iterable[float] = data.get("alphas", [])
    delta_t: float = data.get("delta_t", 1.0)
    tau: float = data.get("tau", 1.0)
    sigma: float = data.get("sigma", 1.0)
    threshold: float = data.get("threshold", float("inf"))

    echo = 0.0
    for k, alpha in enumerate(alphas, start=1):
        echo += alpha * math.exp(-k * delta_t / tau)

    qe = echo ** 2 / sigma if sigma != 0 else 0.0

    action = 0
    if qe > threshold and echo != 0:
        action = -1 if echo > 0 else 1

    return {"echo_amplitude": echo, "qe": qe, "action": action}

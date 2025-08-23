"""Quantum Liquidity Echo indicator module."""

# Source: docs/alphadocs/ideas/gpt5pro/quantum-liquidity-echo-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "quantum_liquidity_echo",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.quantum_liquidity_echo import quantum_liquidity_echo
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node

from strategies.utils.cacheview_helpers import fetch_series


def quantum_liquidity_echo_node(data: dict, view: CacheView | None = None) -> dict:
    """Estimate echo amplitude and amplification index with threshold logic.

    Parameters
    ----------
    data:
        Mapping of parameters. Provide ``alphas`` explicitly or pass a ``source``
        :class:`~qmtl.sdk.node.Node` along with a ``CacheView`` to pull the
        sequence from cached history. When reading from ``view`` supply
        ``side``, ``level`` and ``feature`` to locate values keyed by
        ``(time, side, level, feature)``.
    view:
        Optional :class:`~qmtl.sdk.cache_view.CacheView` supplying cached data
        for ``source`` when ``alphas`` are not precomputed. The cache hierarchy
        is ``view[source][time][side][level][feature]``.
    """

    alphas = data.get("alphas")
    if alphas is None and view is not None and isinstance(data.get("source"), Node):
        src: Node = data["source"]
        side = data.get("side")
        level = data.get("level")
        feature = data.get("feature")
        if side is not None and level is not None and feature is not None:
            alphas = fetch_series(view, src, side, level, feature)

    alphas = alphas or []
    delta_t = data.get("delta_t", 1.0)
    tau = data.get("tau", 1.0)
    sigma = data.get("sigma", 1.0)
    threshold = data.get("threshold", float("inf"))

    echo, qe, action = quantum_liquidity_echo(alphas, delta_t, tau, sigma, threshold)

    return {"echo_amplitude": echo, "qe": qe, "action": action}

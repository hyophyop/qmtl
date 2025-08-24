# Source: docs/alphadocs/ideas/gpt5pro/Order Book Inertia Theory.md
"""Order Book Inertia indicator module.

Computes a simple Order Book Inertia Index (OBII) defined as::

    OBII = (stale_quotes / total_quotes) * 1 / (requote_speed + epsilon)

The result is combined with a queue imbalance to produce a directional
alpha. Inputs are cached by timestamp for reuse across invocations.
"""

from __future__ import annotations

from qmtl.common import FourDimCache

TAGS = {
    "scope": "indicator",
    "family": "order_book_inertia",
    "interval": "1d",
    "asset": "sample",
}

CACHE = FourDimCache()


def order_book_inertia(
    stale_quotes: float,
    total_quotes: float,
    requote_speed: float,
    eps: float,
) -> float:
    """Compute Order Book Inertia Index."""
    if total_quotes <= 0:
        return 0.0
    return (stale_quotes / total_quotes) * (1.0 / (requote_speed + eps))


def order_book_inertia_node(
    data: dict, cache: FourDimCache | None = None
) -> dict:
    """Compute OBII and directional alpha.

    Parameters
    ----------
    data:
        Mapping with optional keys ``timestamp``, ``stale_quotes``, ``total_quotes``,
        ``requote_speed``, ``qi`` and ``epsilon``.
    cache:
        Optional :class:`~qmtl.common.FourDimCache` instance. Defaults to a
        module-level cache.
    """

    cache = cache or CACHE
    ts = data.get("timestamp")

    def _metric(name: str):
        val = data.get(name)
        if ts is not None:
            if val is None:
                val = cache.get(ts, "both", 0, name)
            else:
                cache.set(ts, "both", 0, name, val)
        return val

    stale = float(_metric("stale_quotes") or 0.0)
    total = float(_metric("total_quotes") or 1.0)
    speed = float(_metric("requote_speed") or 0.0)
    qi = float(_metric("qi") or 0.0)
    eps = float(data.get("epsilon", 1e-9))

    obii = order_book_inertia(stale, total, speed, eps)
    alpha = obii * qi

    if ts is not None:
        cache.set(ts, "both", 0, "obii", obii)
        cache.set(ts, "both", 0, "alpha", alpha)

    return {"obii": obii, "alpha": alpha}

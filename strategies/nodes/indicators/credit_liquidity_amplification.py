"""Credit-Liquidity Amplification indicator module."""

# Source: docs/alphadocs/ideas/gpt5pro/Credit-Liquidity Amplification Theory.md
# Priority: gpt5pro

from qmtl.transforms.credit_liquidity_amplification import credit_liquidity_amplification
from qmtl.sdk.cache_view import CacheView

TAGS = {
    "scope": "indicator",
    "family": "credit_liquidity_amplification",
    "interval": "1d",
    "asset": "macro",
}


def credit_liquidity_amplification_node(data: dict, view: CacheView | None = None) -> dict:
    """Compute CLAMP probability from factor series.

    Parameters
    ----------
    data:
        Mapping with series ``ebp``, ``cdx``, ``ccbs``, ``ust_liq``, ``amihud`` and ``move``.
    view:
        Unused placeholder for compatibility with other nodes.

    Returns
    -------
    dict
        Dictionary containing the ``clamp`` probability.
    """

    ebp = data.get("ebp", [])
    cdx = data.get("cdx", [])
    ccbs = data.get("ccbs", [])
    ust_liq = data.get("ust_liq", [])
    amihud = data.get("amihud", [])
    move = data.get("move", [])

    b = data.get("b")
    c = data.get("c")
    alpha = data.get("alpha")

    prob = credit_liquidity_amplification(ebp, cdx, ccbs, ust_liq, amihud, move, b, c, alpha)
    return {"clamp": prob}

"""Generate basic trade signals from alpha values."""

TAGS = {
    "scope": "transform",
    "family": "trade_signal",
    "interval": "1d",
    "asset": "sample",
}


def threshold_signal_node(alpha: float, *, long_threshold: float, short_threshold: float, size: float = 1.0) -> dict:
    """Return a trade signal based on threshold comparison.

    Parameters
    ----------
    alpha:
        Latest alpha value.
    long_threshold:
        Minimum alpha required to issue a ``BUY`` signal.
    short_threshold:
        Maximum alpha allowed to issue a ``SELL`` signal.
    size:
        Absolute trade size for ``BUY`` or ``SELL`` actions.
    """

    if alpha >= long_threshold:
        action = "BUY"
    elif alpha <= short_threshold:
        action = "SELL"
    else:
        action = "HOLD"
    return {"action": action, "size": size}

"""Indicator node processors."""

from collections.abc import Callable, Sequence

from qmtl.sdk.node import Node
from qmtl.transforms import alpha_history_node

__all__ = ["sample_indicator", "alpha_indicator_with_history"]


def sample_indicator(data: dict) -> int | float:
    """Double the ``value`` entry of the input mapping.

    Parameters
    ----------
    data:
        Mapping that may include a ``"value"`` key with a numeric value.

    Returns
    -------
    int | float
        Twice the numeric ``value`` if provided, otherwise ``0".
    """

    return data.get("value", 0) * 2


def alpha_indicator_with_history(
    compute_fn: Callable,
    inputs: Sequence[Node] | None = None,
    *,
    window: int = 20,
    interval: int | str = "1s",
    period: int = 1,
    name: str | None = None,
) -> Node:
    """Return ``compute_fn`` wrapped with ``alpha_history_node``.

    Parameters
    ----------
    compute_fn:
        Node processor returning a mapping with an ``"alpha"`` value.
    inputs:
        Upstream nodes supplying the inputs for ``compute_fn``.
    window:
        Number of recent alpha values retained in history.
    interval:
        Bar interval for the resulting node.
    period:
        Number of bars to retain in the cache.
    name:
        Optional name for the inner alpha node.

    Returns
    -------
    Node
        Node emitting a sliding window of alpha values.
    """

    def wrapped(view):
        result = compute_fn(view)
        return result.get("alpha")

    base = Node(
        input=list(inputs) if inputs else None,
        compute_fn=wrapped,
        name=name or compute_fn.__name__,
        interval=interval,
        period=period,
    )
    return alpha_history_node(base, window=window, name=f"{base.name}_history")


"""Helper utilities for indicator nodes."""

from collections.abc import Callable, Sequence

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.transforms import alpha_history_node

__all__ = ["alpha_indicator_with_history"]


def alpha_indicator_with_history(
    compute_fn: Callable,
    inputs: Sequence[Node] | None = None,
    *,
    window: int = 20,
    interval: int | str = "1s",
    period: int = 1,
    name: str | None = None,
) -> Node:
    """Wrap ``compute_fn`` with ``alpha_history_node``.

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

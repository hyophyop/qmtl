"""Alpha history transformation node."""

from collections import deque

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def alpha_history_node(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node accumulating alpha values over a fixed window.

    The node keeps a sliding window of the latest ``window`` values from the
    upstream ``source`` node and returns them as a list on each computation.
    """

    history = deque(maxlen=window)

    def compute(view: CacheView):
        data = view[source][source.interval]
        if not data:
            return None
        value = data[-1][1]
        history.append(value)
        return list(history)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "alpha_history",
        interval=source.interval,
        period=window,
    )

"""Alpha history transformation node."""

from collections import deque
from collections.abc import Callable
from typing import Any

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def alpha_history_node(
    source: Node,
    window: int,
    *,
    select_fn: Callable[[Any], Any] | None = None,
    name: str | None = None,
) -> Node:
    """Return a Node accumulating values from ``source`` over a fixed window.

    Parameters
    ----------
    source:
        Upstream node providing a sequence of payloads.
    window:
        Number of recent values to retain.
    select_fn:
        Callback extracting the desired value from the latest upstream payload.
        Defaults to the identity function, returning the raw payload value.
    name:
        Optional name for the resulting node.

    The node keeps a sliding window of the latest ``window`` values extracted by
    ``select_fn`` from the upstream ``source`` node and returns them as a list on
    each computation.
    """

    selector = select_fn or (lambda x: x)
    history = deque(maxlen=window)

    def compute(view: CacheView):
        data = view[source][source.interval]
        if not data:
            return None
        payload = data[-1][1]
        history.append(selector(payload))
        return list(history)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "alpha_history",
        interval=source.interval,
        period=1,
    )

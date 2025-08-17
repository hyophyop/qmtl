"""Order book depth related transformation nodes."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def depth_change_node(source: Node, *, name: str | None = None) -> Node:
    """Return a node computing total depth change between adjacent snapshots.

    Parameters
    ----------
    source:
        Node yielding order book depth snapshots. Each snapshot is expected to
        provide ``"bids"`` and ``"asks"`` sequences where each level may be a
        ``(price, size)`` pair or a raw size value.
    name:
        Optional node name. Defaults to ``"depth_change"``.

    Returns
    -------
    Node
        Node emitting the depth difference ``current_depth - previous_depth``.
    """

    def _total_depth(snapshot: dict) -> float:
        depth = 0.0
        for side in ("bids", "asks"):
            levels = snapshot.get(side, [])
            for level in levels:
                if isinstance(level, (list, tuple)):
                    if not level:
                        continue
                    # Treat ``(price, size)`` or ``(size,)`` forms
                    size = level[1] if len(level) > 1 else level[0]
                else:
                    size = level
                depth += float(size)
        return depth

    def compute(view: CacheView):
        data = view[source][source.interval][-2:]
        if len(data) < 2:
            return None
        prev = data[0][1]
        curr = data[1][1]
        return _total_depth(curr) - _total_depth(prev)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "depth_change",
        interval=source.interval,
        period=2,
    )

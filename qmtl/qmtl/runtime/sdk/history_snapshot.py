from __future__ import annotations

import logging
from typing import Iterable

from . import snapshot as snap
from .strategy import Strategy

logger = logging.getLogger(__name__)


def _iter_stream_nodes(strategy: Strategy) -> Iterable[object]:
    from .node import StreamInput

    for node in strategy.nodes:
        if isinstance(node, StreamInput) and node.interval is not None and node.period:
            yield node


def hydrate_strategy_snapshots(strategy: Strategy) -> int:
    """Hydrate eligible stream nodes from persisted snapshots.

    Returns the number of nodes hydrated.
    """

    count = 0
    for node in _iter_stream_nodes(strategy):
        try:
            strict = False
            try:
                strict = getattr(node, "runtime_compat", "loose") == "strict"
            except Exception:
                strict = False
            if snap.hydrate(node, strict_runtime=strict):
                count += 1
        except Exception:  # pragma: no cover - defensive against user nodes
            logger.exception("snapshot hydration failed for %s", getattr(node, "node_id", "<unknown>"))
    if count:
        logger.info("hydrated %d nodes from snapshots", count)
    return count


def write_strategy_snapshots(strategy: Strategy) -> int:
    """Write snapshots for eligible stream nodes.

    Returns the number of snapshot files written.
    """

    count = 0
    for node in _iter_stream_nodes(strategy):
        try:
            path = snap.write_snapshot(node)
            if path:
                count += 1
        except Exception:  # pragma: no cover - defensive against user nodes
            logger.exception("snapshot write failed for %s", getattr(node, "node_id", "<unknown>"))
    if count:
        logger.info("wrote %d node snapshots", count)
    return count


__all__ = ["hydrate_strategy_snapshots", "write_strategy_snapshots"]

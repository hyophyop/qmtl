"""Calculate market impact factor."""

# Source: docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md

TAGS = {
    "scope": "indicator",
    "family": "impact",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.indicators import impact_node as qmtl_impact_node
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def impact_node(data):
    """Compute liquidity-adjusted market impact using qmtl feature."""
    volume = data.get("volume", 0.0)
    avg_volume = data.get("avg_volume", 1.0)
    depth = data.get("depth", 1.0)
    beta = data.get("beta", 1.0)

    vol_node = SourceNode(interval="1s", period=1, config={"id": "volume"})
    avg_node = SourceNode(interval="1s", period=1, config={"id": "avg_volume"})
    depth_node = SourceNode(interval="1s", period=1, config={"id": "depth"})
    node = qmtl_impact_node(vol_node, avg_node, depth_node, beta=beta)

    view = CacheView(
        {
            vol_node.node_id: {1: [(0, volume)]},
            avg_node.node_id: {1: [(0, avg_volume)]},
            depth_node.node_id: {1: [(0, depth)]},
        }
    )
    result = node.compute_fn(view) or 0.0
    return {"impact": result}

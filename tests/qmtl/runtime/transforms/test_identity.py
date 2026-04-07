import polars as pl
from polars.testing import assert_frame_equal

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node, SourceNode
from qmtl.runtime.transforms import identity_transform_node


def test_identity_collects_payloads_into_dataframe():
    source = SourceNode(interval="1s", period=3, config={"id": "src"})
    node = Node(
        input=source,
        compute_fn=identity_transform_node,
        interval="1s",
        period=3,
    )
    data = {source.node_id: {1: [(0, {"p": 1}), (1, {"p": 2})]}}
    view = CacheView(data)
    df = node.compute_fn(view)
    expected = pl.DataFrame([{"p": 1}, {"p": 2}])
    assert_frame_equal(df, expected)

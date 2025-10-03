from qmtl.runtime.transforms import execution_imbalance_node, rate_of_change
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.sdk.cache_view import CacheView


def test_execution_imbalance_compute():
    buy = SourceNode(interval="1s", period=3, config={"id": "buy"})
    sell = SourceNode(interval="1s", period=3, config={"id": "sell"})
    node = execution_imbalance_node(buy, sell)
    data = {
        buy.node_id: {1: [(0, 60)]},
        sell.node_id: {1: [(0, 40)]},
    }
    view = CacheView(data)
    assert node.compute_fn(view) == 0.2


def test_execution_imbalance_derivative():
    buy = SourceNode(interval="1s", period=3, config={"id": "buy"})
    sell = SourceNode(interval="1s", period=3, config={"id": "sell"})
    node = execution_imbalance_node(buy, sell)

    data0 = {
        buy.node_id: {1: [(0, 60)]},
        sell.node_id: {1: [(0, 40)]},
    }
    val0 = node.compute_fn(CacheView(data0))

    data1 = {
        buy.node_id: {1: [(0, 60), (1, 30)]},
        sell.node_id: {1: [(0, 40), (1, 70)]},
    }
    val1 = node.compute_fn(CacheView(data1))

    imb_data = {node.node_id: {1: [(0, val0), (1, val1)]}}
    view = CacheView(imb_data)
    deriv_node = rate_of_change(node, period=2)
    assert deriv_node.compute_fn(view) == (val1 - val0) / val0

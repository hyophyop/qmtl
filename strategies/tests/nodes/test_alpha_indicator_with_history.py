from qmtl.indicators import alpha_indicator_with_history
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_alpha_indicator_history_window():
    src = SourceNode(interval="1s", period=1, config={"id": "val"})

    def dummy_alpha(view: CacheView):
        latest = view[src][src.interval][-1][1]
        return {"alpha": latest}

    history = alpha_indicator_with_history(
        dummy_alpha, inputs=[src], window=2, name="dummy_alpha"
    )

    assert history.input.name == "dummy_alpha"
    assert history.name == "dummy_alpha_history"

    src_view1 = CacheView({src.node_id: {1: [(0, 1.0)]}})
    alpha1 = history.input.compute_fn(src_view1)
    view1 = CacheView({history.input.node_id: {1: [(0, alpha1)]}})
    assert history.compute_fn(view1) == [alpha1]

    src_view2 = CacheView({src.node_id: {1: [(1, 2.0)]}})
    alpha2 = history.input.compute_fn(src_view2)
    view2 = CacheView({history.input.node_id: {1: [(1, alpha2)]}})
    assert history.compute_fn(view2) == [alpha1, alpha2]

    src_view3 = CacheView({src.node_id: {1: [(2, 3.0)]}})
    alpha3 = history.input.compute_fn(src_view3)
    view3 = CacheView({history.input.node_id: {1: [(2, alpha3)]}})
    assert history.compute_fn(view3) == [alpha2, alpha3]

import math

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import SourceNode

from strategies.nodes.indicators.non_linear_alpha import non_linear_alpha_node
from strategies.utils.cacheview_helpers import fetch_series, latest_value


def test_cache_assisted_execution():
    q_src = SourceNode(interval=1, period=1, config={"id": "Q"})
    v_src = SourceNode(interval=1, period=1, config={"id": "V"})
    depth_src = SourceNode(interval=1, period=1, config={"id": "depth"})
    vol_src = SourceNode(interval=1, period=1, config={"id": "vol"})
    obi_src = SourceNode(interval=1, period=2, config={"id": "obi"})

    q_val = 100.0
    v_val = 400.0
    depth_val = 10.0
    vol_val = 0.2
    obi_hist = [(0, 0.5), (1, 0.6)]

    view = CacheView(
        {
            q_src.node_id: {q_src.interval: [(0, q_val)]},
            v_src.node_id: {v_src.interval: [(0, v_val)]},
            depth_src.node_id: {depth_src.interval: [(0, depth_val)]},
            vol_src.node_id: {vol_src.interval: [(0, vol_val)]},
            obi_src.node_id: {obi_src.interval: obi_hist},
        }
    )

    out = non_linear_alpha_node(
        {
            "Q": q_src,
            "V": v_src,
            "depth": depth_src,
            "beta": 1.0,
            "volatility": vol_src,
            "obi": obi_src,
            "gamma": 1.0,
        },
        view,
    )

    q_resolved = latest_value(view, q_src)
    v_resolved = latest_value(view, v_src)
    depth_resolved = latest_value(view, depth_src)
    vol_val_resolved = latest_value(view, vol_src)
    expected_impact = math.sqrt(q_resolved / v_resolved) / depth_resolved**1.0
    obi_series = fetch_series(view, obi_src)
    expected_obi_deriv = (obi_series[-1] - obi_series[-2]) / obi_series[-2]
    expected_alpha = math.tanh(expected_impact * vol_val_resolved) * expected_obi_deriv

    assert math.isclose(out["impact"], expected_impact)
    assert math.isclose(out["volatility"], vol_val_resolved)
    assert math.isclose(out["obi_derivative"], expected_obi_deriv)
    assert math.isclose(out["alpha"], expected_alpha)

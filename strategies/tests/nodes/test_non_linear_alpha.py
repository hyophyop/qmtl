import math

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import SourceNode

from strategies.nodes.indicators.non_linear_alpha import non_linear_alpha_node
from strategies.utils.cacheview_helpers import fetch_series, latest_value


def test_cache_assisted_execution():
    impact_src = SourceNode(interval=1, period=1, config={"id": "impact"})
    vol_src = SourceNode(interval=1, period=1, config={"id": "vol"})
    obi_src = SourceNode(interval=1, period=2, config={"id": "obi"})

    impact_val = 0.1
    vol_val = 0.2
    obi_hist = [(0, 0.5), (1, 0.6)]

    view = CacheView(
        {
            impact_src.node_id: {impact_src.interval: [(0, impact_val)]},
            vol_src.node_id: {vol_src.interval: [(0, vol_val)]},
            obi_src.node_id: {obi_src.interval: obi_hist},
        }
    )

    out = non_linear_alpha_node(
        {
            "impact": impact_src,
            "volatility": vol_src,
            "obi": obi_src,
            "gamma": 1.0,
        },
        view,
    )

    impact_val_resolved = latest_value(view, impact_src)
    vol_val_resolved = latest_value(view, vol_src)
    obi_series = fetch_series(view, obi_src)
    expected_obi_deriv = (obi_series[-1] - obi_series[-2]) / obi_series[-2]
    expected_alpha = math.tanh(impact_val_resolved * vol_val_resolved) * expected_obi_deriv

    assert math.isclose(out["impact"], impact_val_resolved)
    assert math.isclose(out["volatility"], vol_val_resolved)
    assert math.isclose(out["obi_derivative"], expected_obi_deriv)
    assert math.isclose(out["alpha"], expected_alpha)

from qmtl.transforms.linearity_metrics import equity_linearity_metrics


def test_equity_linearity_perfect_linear_up():
    y = [0, 1, 2, 3, 4, 5]
    m = equity_linearity_metrics(y)
    assert m["net_gain"] > 0
    assert m["r2_up"] > 0.999
    assert m["straightness_ratio"] > 0.999
    assert m["monotonicity"] == 1.0
    assert m["new_high_frac"] == 1.0
    assert m["score"] > 0.95


def test_equity_linearity_zigzag_up_is_lower():
    y_lin = [0, 1, 2, 3, 4, 5]
    y_zig = [0, 1, 0.5, 1.5, 1.0, 2.0]
    m_lin = equity_linearity_metrics(y_lin)
    m_zig = equity_linearity_metrics(y_zig)
    assert m_zig["net_gain"] > 0
    assert m_zig["score"] < m_lin["score"]
    assert m_zig["straightness_ratio"] < m_lin["straightness_ratio"]
    assert m_zig["r2_up"] < m_lin["r2_up"]


def test_equity_linearity_negative_trend_scores_zero():
    y = [5, 4, 3, 2, 1, 0]
    m = equity_linearity_metrics(y)
    assert m["net_gain"] < 0
    assert m["r2_up"] == 0.0  # slope negative
    assert m["score"] == 0.0


def test_equity_linearity_flat_series():
    y = [1, 1, 1, 1]
    m = equity_linearity_metrics(y)
    assert m["net_gain"] == 0
    assert m["straightness_ratio"] == 0.0
    assert m["score"] == 0.0


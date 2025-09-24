from qmtl.runtime.transforms.linearity_metrics import equity_linearity_metrics_v2


def test_v2_linear_up_is_high():
    y = [0, 1, 2, 3, 4, 5]
    m = equity_linearity_metrics_v2(y)
    assert m["net_gain"] > 0
    assert m["tvr"] > 0.95
    assert m["tuw"] < 0.05
    assert m["r2_up"] > 0.99
    assert m["spearman_rho"] > 0.99
    assert m["score"] > 0.9


def test_v2_flat_then_jump_penalized():
    # Long flat, then single jump at end
    y = [0.0] * 50 + [1.0]
    m = equity_linearity_metrics_v2(y)
    # TUW high (most time under water)
    assert m["tuw"] > 0.8
    # Score should be low despite positive net gain
    assert m["score"] < 0.2


def test_v2_zigzag_penalized_vs_linear():
    y_lin = [0, 1, 2, 3, 4, 5]
    y_zig = [0, 1, 0, 2, 1, 3]
    m_lin = equity_linearity_metrics_v2(y_lin)
    m_zig = equity_linearity_metrics_v2(y_zig)
    assert m_zig["tvr"] < m_lin["tvr"]
    assert m_zig["tuw"] > m_lin["tuw"]
    assert m_zig["score"] < m_lin["score"]


def test_v2_downtrend_with_orientation_down():
    y_down = [5, 4, 3, 2, 1, 0]
    m_up = equity_linearity_metrics_v2(y_down, orientation="up")
    m_dn = equity_linearity_metrics_v2(y_down, orientation="down")
    # Up orientation gives zero score due to wrong direction
    assert m_up["score"] == 0.0
    # Down orientation should capture linearity and yield high score
    assert m_dn["score"] > 0.8

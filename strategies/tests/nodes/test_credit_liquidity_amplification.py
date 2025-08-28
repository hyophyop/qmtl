from strategies.nodes.indicators.credit_liquidity_amplification import (
    credit_liquidity_amplification_node,
)


def test_credit_liquidity_amplification_node_returns_probability():
    data = {
        "ebp": [0.1, 0.2, 0.3],
        "cdx": [0.05, 0.1, 0.15],
        "ccbs": [0.01, 0.02, 0.03],
        "ust_liq": [1.0, 1.1, 1.2],
        "amihud": [2.0, 2.1, 2.2],
        "move": [0.4, 0.5, 0.6],
    }
    result = credit_liquidity_amplification_node(data)
    assert 0.0 <= result["clamp"] <= 1.0

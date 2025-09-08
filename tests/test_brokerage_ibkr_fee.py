import pytest
from qmtl.brokerage import IBKRFeeModel, OrderType


def test_ibkr_fee_tiers_and_liquidity_components():
    fee = IBKRFeeModel(
        tiers=[(300000, 0.0035)],
        minimum=1.0,
        exchange_fee_remove=0.0008,
        exchange_fee_add=-0.0002,
        regulatory_fee_remove=0.0001,
    )
    # Small market order -> minimum broker fee + venue/regulatory charges
    small = type("O", (), {"quantity": 10, "type": OrderType.MARKET})()
    assert fee.calculate(small, 100.0) == pytest.approx(1.0 + 10 * (0.0008 + 0.0001))
    # Large market order crosses tier and adds per-share charges
    large = type("O", (), {"quantity": 300500, "type": OrderType.MARKET})()
    expected = 300000 * 0.0035 + 500 * 0.0020 + 300500 * (0.0008 + 0.0001)
    assert fee.calculate(large, 100.0) == pytest.approx(expected)


def test_ibkr_fee_add_liquidity_rebate():
    fee = IBKRFeeModel(exchange_fee_add=-0.01, minimum=0.0)
    order = type(
        "O", (), {"quantity": 100, "type": OrderType.LIMIT, "adds_liquidity": True}
    )()
    assert fee.calculate(order, 100.0) == pytest.approx(100 * 0.0035 - 1.0)


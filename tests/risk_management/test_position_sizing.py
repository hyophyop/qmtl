import pytest

from qmtl.sdk.risk_management import RiskManager


def test_calculate_position_size_basic():
    risk_manager = RiskManager(position_size_limit_pct=0.10)

    size = risk_manager.calculate_position_size(
        symbol="AAPL",
        target_allocation_pct=0.05,
        current_price=100.0,
        portfolio_value=100000,
    )

    assert size == pytest.approx(50.0)


def test_calculate_position_size_with_volatility_adjustment():
    risk_manager = RiskManager(position_size_limit_pct=0.10)

    high_vol = risk_manager.calculate_position_size(
        symbol="CRYPTO",
        target_allocation_pct=0.05,
        current_price=100.0,
        portfolio_value=100000,
        current_volatility=0.80,
    )
    low_vol = risk_manager.calculate_position_size(
        symbol="BOND",
        target_allocation_pct=0.05,
        current_price=100.0,
        portfolio_value=100000,
        current_volatility=0.05,
    )

    assert 0 < high_vol < low_vol


@pytest.mark.parametrize(
    "portfolio_value, current_price",
    [
        pytest.param(0.0, 100.0, id="zero-portfolio"),
        pytest.param(100000, 0.0, id="zero-price"),
    ],
)
def test_calculate_position_size_edge_cases(portfolio_value, current_price):
    risk_manager = RiskManager()

    size = risk_manager.calculate_position_size(
        symbol="AAPL",
        target_allocation_pct=0.05,
        current_price=current_price,
        portfolio_value=portfolio_value,
    )

    assert size == 0.0

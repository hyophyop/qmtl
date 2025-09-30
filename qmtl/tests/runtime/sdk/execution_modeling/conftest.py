import pytest

from qmtl.runtime.sdk.execution_modeling import ExecutionModel, MarketData


@pytest.fixture
def execution_model() -> ExecutionModel:
    """Execution model with typical commission and slippage settings."""
    return ExecutionModel(
        commission_rate=0.001,
        commission_minimum=1.0,
        base_slippage_bps=2.0,
        market_impact_coeff=0.1,
        latency_ms=100,
    )


@pytest.fixture
def low_cost_execution_model() -> ExecutionModel:
    """Execution model used for deterministic cost assertions."""
    return ExecutionModel(
        commission_rate=0.001,
        commission_minimum=0.0,
        base_slippage_bps=1.0,
        market_impact_coeff=0.0,
        latency_ms=0,
    )


@pytest.fixture
def liquid_market_data() -> MarketData:
    """Representative market data for a liquid symbol."""
    return MarketData(
        timestamp=1000,
        bid=99.5,
        ask=100.5,
        last=100.0,
        volume=10000,
    )


@pytest.fixture
def quiet_market_data() -> MarketData:
    """Stable market data used for explicit numeric expectations."""
    return MarketData(
        timestamp=0,
        bid=99.0,
        ask=101.0,
        last=100.0,
        volume=10000,
    )

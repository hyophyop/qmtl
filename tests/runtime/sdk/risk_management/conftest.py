import pytest

from qmtl.runtime.sdk.risk_management import PositionInfo, RiskManager


@pytest.fixture
def default_risk_manager() -> RiskManager:
    return RiskManager()


@pytest.fixture
def sample_positions() -> dict[str, PositionInfo]:
    return {
        "AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100),
        "TSLA": PositionInfo("TSLA", 200, 20000, 0, 100, 100),
        "MSFT": PositionInfo("MSFT", 300, 30000, 0, 100, 100),
    }

from unittest.mock import MagicMock

from qmtl.sdk import metrics as sdk_metrics
from qmtl.sdk.runner import Runner
from qmtl.sdk.pretrade import Activation
from qmtl.brokerage import BrokerageModel, CashBuyingPowerModel
from qmtl.brokerage.fees import PercentFeeModel
from qmtl.brokerage.slippage import NullSlippageModel
from qmtl.brokerage.fill_models import MarketFillModel
from qmtl.brokerage.order import Account
from qmtl.common.pretrade import RejectionReason


def _setup_context():
    brokerage = BrokerageModel(
        buying_power_model=CashBuyingPowerModel(),
        fee_model=PercentFeeModel(),
        slippage_model=NullSlippageModel(),
        fill_model=MarketFillModel(),
    )
    account = Account(cash=100_000.0)
    Runner.set_pretrade_context(
        activation_map={"AAPL": Activation(enabled=False, reason="disabled")},
        brokerage=brokerage,
        account=account,
    )


def test_pretrade_chain_off_allows_order(monkeypatch):
    Runner.set_pretrade_chain(False)
    _setup_context()
    service = MagicMock()
    Runner.set_trade_execution_service(service)
    order = {"side": "BUY", "quantity": 1, "symbol": "AAPL", "price": 100.0, "timestamp": 0}
    Runner._handle_trade_order(order)
    service.post_order.assert_called_once_with(order)
    Runner.set_trade_execution_service(None)
    Runner.set_pretrade_context()


def test_pretrade_chain_rejects_and_records_metrics(monkeypatch):
    Runner.set_pretrade_chain(True)
    _setup_context()
    sdk_metrics.reset_metrics()
    sdk_metrics.set_world_id("w1")
    service = MagicMock()
    Runner.set_trade_execution_service(service)
    order = {"side": "BUY", "quantity": 1, "symbol": "AAPL", "price": 100.0, "timestamp": 0}
    Runner._handle_trade_order(order)
    service.post_order.assert_not_called()
    assert sdk_metrics.pretrade_attempts_total._vals["w1"] == 1  # type: ignore[attr-defined]
    key = ("w1", RejectionReason.ACTIVATION_DISABLED.value)
    assert sdk_metrics.pretrade_rejections_total._vals.get(key, 0) == 1  # type: ignore[attr-defined]
    Runner.set_trade_execution_service(None)
    Runner.set_pretrade_chain(False)
    Runner.set_pretrade_context()

from __future__ import annotations

import asyncio

from qmtl.sdk import metrics as sdk_metrics
from qmtl.sdk.pretrade import check_pretrade, Activation
from qmtl.common.pretrade import RejectionReason
from qmtl.brokerage import BrokerageModel, CashBuyingPowerModel
from qmtl.brokerage.fees import PercentFeeModel
from qmtl.brokerage.slippage import NullSlippageModel
from qmtl.brokerage.fill_models import MarketFillModel
from qmtl.brokerage.order import Account
from qmtl.gateway import metrics as gw_metrics
from qmtl.gateway.degradation import DegradationManager
from qmtl.gateway.routes import create_api_router


def test_sdk_pretrade_metrics_activation_reject():
    sdk_metrics.reset_metrics()
    sdk_metrics.set_world_id("w1")

    activation = {"AAPL": Activation(enabled=False, reason="disabled by policy")}
    brokerage = BrokerageModel(
        buying_power_model=CashBuyingPowerModel(),
        fee_model=PercentFeeModel(),
        slippage_model=NullSlippageModel(),
        fill_model=MarketFillModel(),
    )
    account = Account(cash=100_000.0)

    res = check_pretrade(
        activation_map=activation,
        brokerage=brokerage,
        account=account,
        symbol="AAPL",
        quantity=10,
        price=100.0,
    )
    assert not res.allowed
    assert res.reason == RejectionReason.ACTIVATION_DISABLED
    # Attempt and rejection counters should update
    assert sdk_metrics.pretrade_attempts_total._vals["w1"] == 1  # type: ignore[attr-defined]
    key = ("w1", RejectionReason.ACTIVATION_DISABLED.value)
    assert sdk_metrics.pretrade_rejections_total._vals.get(key, 0) == 1  # type: ignore[attr-defined]


def test_gateway_status_includes_pretrade_metrics():
    gw_metrics.reset_metrics()
    gw_metrics.set_world_id("w1")
    # Simulate two attempts, one rejection at gateway
    gw_metrics.record_pretrade_attempt()
    gw_metrics.record_pretrade_attempt()
    gw_metrics.record_pretrade_rejection("activation_disabled")

    stats = gw_metrics.get_pretrade_stats()
    assert stats["attempts"] >= 2
    assert stats["rejections"].get("activation_disabled", 0) >= 1
    assert 0 <= stats["ratio"] <= 1

    # Build API router and call status endpoint
    router = create_api_router(
        manager=None,
        redis_conn=None,
        database_obj=None,
        dagmanager=None,
        ws_hub=None,
        degradation=DegradationManager(None, None, None),
        world_client=None,
        enforce_live_guard=False,
        accept_legacy_nodeids=True,
    )

    # Extract the status endpoint and execute
    status_func = next(r.endpoint for r in router.routes if getattr(r, "path", None) == "/status")
    result = asyncio.run(status_func())
    assert "pretrade" in result
    assert "degrade_level" in result


from __future__ import annotations

import asyncio

from qmtl.sdk import metrics as sdk_metrics
from qmtl.sdk.pretrade import check_pretrade, Activation
from qmtl.common.pretrade import RejectionReason
from qmtl.brokerage import BrokerageModel
from qmtl.brokerage.simple import CashBuyingPowerModel
from qmtl.brokerage.fees import PercentFeeModel
from qmtl.brokerage.slippage import NullSlippageModel
from qmtl.brokerage.fill_models import MarketFillModel
from qmtl.brokerage.order import Account
from qmtl.gateway.metrics import (
    record_pretrade_attempt as gw_record_attempt,
    record_pretrade_rejection as gw_record_rej,
    get_pretrade_stats,
)
from qmtl.gateway.degradation import DegradationManager
from qmtl.gateway.routes import create_api_router


def test_sdk_pretrade_metrics_activation_reject():
    sdk_metrics.reset_metrics()

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
    assert sdk_metrics.pretrade_attempts_total._val == 1  # type: ignore[attr-defined]
    assert sdk_metrics.pretrade_rejections_total._vals.get(RejectionReason.ACTIVATION_DISABLED.value, 0) == 1  # type: ignore[attr-defined]


def test_gateway_status_includes_pretrade_metrics():
    # Simulate two attempts, one rejection at gateway
    gw_record_attempt()
    gw_record_attempt()
    gw_record_rej("activation_disabled")

    stats = get_pretrade_stats()
    assert stats["attempts"] >= 2
    assert stats["rejections"].get("activation_disabled", 0) >= 1
    assert 0 <= stats["ratio"] <= 1

    # Build API router and call status endpoint
    router = create_api_router(
        manager=None,
        redis_conn=None,
        database_obj=None,
        dagmanager=None,
        watch_hub=None,
        ws_hub=None,
        degradation=DegradationManager(None, None, None),
        world_client=None,
        enforce_live_guard=False,
    )

    # Extract the status endpoint and execute
    status_func = next(r.endpoint for r in router.routes if getattr(r, "path", None) == "/status")
    result = asyncio.get_event_loop().run_until_complete(status_func())
    assert "pretrade" in result
    assert "degrade_level" in result


from qmtl.foundation.schema import (
    OrderAck,
    OrderPayload,
    ExecutionFillEvent,
    PortfolioSnapshot,
    SchemaRegistryClient,
    register_order_schemas,
)


def test_register_order_schemas():
    reg = SchemaRegistryClient()
    register_order_schemas(reg)
    assert reg.latest("OrderPayload")
    assert reg.latest("OrderAck")
    assert reg.latest("ExecutionFillEvent")
    assert reg.latest("PortfolioSnapshot")


def test_order_payload_allows_extra():
    payload = OrderPayload(
        world_id="w1",
        strategy_id="s1",
        correlation_id="c1",
        symbol="BTC/USDT",
        side="BUY",
        type="limit",
        quantity=1.0,
        time_in_force="GTC",
        timestamp=1,
        foo="bar",
    )
    assert payload.extra["foo"] == "bar"

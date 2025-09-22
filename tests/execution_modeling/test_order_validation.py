import pytest

from qmtl.sdk.execution_modeling import OrderSide


def test_validate_order_success(execution_model, liquid_market_data):
    is_valid, message = execution_model.validate_order(
        OrderSide.BUY,
        quantity=100,
        price=100.0,
        market_data=liquid_market_data,
    )

    assert is_valid
    assert message == "Valid"


@pytest.mark.parametrize(
    "side, quantity, price, expected_phrase",
    [
        pytest.param(OrderSide.BUY, -100, 100.0, "quantity", id="negative-quantity"),
        pytest.param(OrderSide.BUY, 100, -100.0, "price", id="negative-price"),
        pytest.param(OrderSide.BUY, 100, 200.0, "above", id="buy-too-high"),
        pytest.param(OrderSide.SELL, 100, 50.0, "below", id="sell-too-low"),
    ],
)
def test_validate_order_failure_messages(execution_model, liquid_market_data, side, quantity, price, expected_phrase):
    is_valid, message = execution_model.validate_order(side, quantity, price, liquid_market_data)

    assert not is_valid
    assert expected_phrase in message.lower()

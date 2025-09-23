from __future__ import annotations

import pytest

from qmtl.sdk.execution_modeling import (
    MarketData,
    apply_latency,
    calculate_market_impact,
    determine_fill_quantity,
)


def make_market_data(*, volume: float) -> MarketData:
    return MarketData(timestamp=1, bid=99.5, ask=100.5, last=100.0, volume=volume)


def test_market_impact_zero_volume() -> None:
    market_data = make_market_data(volume=0.0)
    impact = calculate_market_impact(10.0, market_data, coeff=0.2)
    assert impact == 0.0


def test_determine_fill_quantity_respects_partial_flag() -> None:
    remaining = 10.0
    result = determine_fill_quantity(
        remaining,
        allow_partial=False,
        max_partial_fill=5.0,
    )
    assert result is None

    partial_result = determine_fill_quantity(
        remaining,
        allow_partial=True,
        max_partial_fill=5.0,
    )
    assert partial_result == pytest.approx(5.0)


def test_apply_latency_handles_zero_and_negative() -> None:
    assert apply_latency(1000, 0) == 1000
    with pytest.raises(ValueError):
        apply_latency(1000, -1)


@pytest.mark.parametrize(
    "quantity,expected_sign",
    [
        (5.0, 1),
        (0.0, 0),
    ],
)
def test_market_impact_quantity_boundary(quantity: float, expected_sign: int) -> None:
    market_data = make_market_data(volume=100.0)
    impact = calculate_market_impact(quantity, market_data, coeff=0.2)
    if expected_sign == 0:
        assert impact == 0.0
    else:
        assert impact > 0.0

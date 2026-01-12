from __future__ import annotations

from datetime import datetime

import pytest

from qmtl.runtime.labeling.barriers import volatility_scaled_barrier_spec
from qmtl.runtime.labeling.schema import BarrierMode


def test_volatility_scaled_barrier_spec_long() -> None:
    ts = datetime(2025, 1, 1)
    spec = volatility_scaled_barrier_spec(
        price=100.0,
        sigma=0.02,
        profit_multiplier=2.0,
        stop_multiplier=3.0,
        side="long",
        frozen_at=ts,
    )

    assert spec.mode == BarrierMode.PRICE
    assert spec.profit_target == pytest.approx(104.0)
    assert spec.stop_loss == pytest.approx(94.0)
    assert spec.frozen_at == ts


def test_volatility_scaled_barrier_spec_short() -> None:
    spec = volatility_scaled_barrier_spec(
        price=100.0,
        sigma=0.02,
        profit_multiplier=2.0,
        stop_multiplier=3.0,
        side="short",
    )

    assert spec.profit_target == pytest.approx(96.0)
    assert spec.stop_loss == pytest.approx(106.0)


def test_volatility_scaled_barrier_spec_allows_missing_barriers() -> None:
    spec = volatility_scaled_barrier_spec(
        price=100.0,
        sigma=0.02,
        profit_multiplier=None,
        stop_multiplier=None,
        side="buy",
    )

    assert spec.profit_target is None
    assert spec.stop_loss is None


def test_volatility_scaled_barrier_spec_rejects_invalid_side() -> None:
    with pytest.raises(ValueError, match="side must be one of"):
        volatility_scaled_barrier_spec(
            price=100.0,
            sigma=0.02,
            profit_multiplier=1.0,
            stop_multiplier=1.0,
            side="invalid",
        )


def test_volatility_scaled_barrier_spec_return_mode() -> None:
    spec = volatility_scaled_barrier_spec(
        price=200.0,
        sigma=0.015,
        profit_multiplier=1.5,
        stop_multiplier=2.0,
        side="sell",
        mode=BarrierMode.RETURN,
    )

    assert spec.mode == BarrierMode.RETURN
    assert spec.profit_target == pytest.approx(0.0225)
    assert spec.stop_loss == pytest.approx(0.03)


def test_volatility_scaled_barrier_spec_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        volatility_scaled_barrier_spec(
            price=100.0,
            sigma=0.02,
            profit_multiplier=1.0,
            stop_multiplier=1.0,
            side="long",
            mode="invalid",  # type: ignore[arg-type]
        )

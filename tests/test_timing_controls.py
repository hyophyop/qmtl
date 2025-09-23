"""Concise tests for timing controls behaviour."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Iterable

import pytest

from qmtl.sdk import Strategy, StreamInput
from qmtl.sdk.timing_controls import (
    MarketHours,
    MarketSession,
    TimingController,
    validate_backtest_timing,
)


UTC = timezone.utc


def dt_utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Return an aware UTC datetime for convenience inside tests."""

    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def to_millis(timestamp: datetime) -> int:
    """Convert a timezone aware datetime into milliseconds since epoch."""

    return int(timestamp.timestamp() * 1000)


@pytest.fixture
def default_market_hours() -> MarketHours:
    """Provide canonical U.S. equity market hours for tests."""

    return MarketHours(
        pre_market_start=time(4, 0),
        regular_start=time(9, 30),
        regular_end=time(16, 0),
        post_market_end=time(20, 0),
    )


@pytest.fixture
def timing_controller(default_market_hours: MarketHours) -> TimingController:
    """Create a controller bound to the default market hours."""

    return TimingController(market_hours=default_market_hours)


@pytest.fixture
def stream_strategy() -> Strategy:
    """Strategy fixture with a single hourly stream input."""

    class SingleStreamStrategy(Strategy):
        def setup(self) -> None:  # pragma: no cover - exercised via tests
            stream = StreamInput(interval="3600s", period=10)
            self.add_nodes([stream])

    strategy = SingleStreamStrategy()
    strategy.setup()
    return strategy


def populate_stream(strategy: Strategy, timestamps: Iterable[datetime]) -> None:
    """Append samples for the supplied timestamps into the stream cache."""

    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            for idx, timestamp in enumerate(timestamps):
                node.cache.append(
                    "test_queue",
                    3600,
                    to_millis(timestamp),
                    {"close": 100.0 + idx},
                )


@pytest.mark.parametrize(
    ("timestamp", "expected_session"),
    (
        pytest.param(dt_utc(2024, 1, 3, 10, 30), MarketSession.REGULAR, id="regular"),
        pytest.param(dt_utc(2024, 1, 3, 8, 0), MarketSession.PRE_MARKET, id="pre-market"),
        pytest.param(dt_utc(2024, 1, 3, 18, 0), MarketSession.POST_MARKET, id="post-market"),
        pytest.param(dt_utc(2024, 1, 3, 2, 0), MarketSession.CLOSED, id="overnight"),
        pytest.param(dt_utc(2024, 1, 6, 10, 0), MarketSession.CLOSED, id="saturday"),
        pytest.param(dt_utc(2024, 1, 7, 14, 0), MarketSession.CLOSED, id="sunday"),
    ),
)
def test_market_session_identification(
    default_market_hours: MarketHours, timestamp: datetime, expected_session: MarketSession
) -> None:
    """Market sessions are correctly classified for representative timestamps."""

    assert default_market_hours.get_session(timestamp) == expected_session


def test_timing_controller_defaults() -> None:
    """TimingController exposes sensible defaults."""

    controller = TimingController()

    assert controller.min_execution_delay_ms == 50
    assert controller.max_execution_delay_ms == 500
    assert controller.allow_pre_post_market is False
    assert controller.require_regular_hours is False
    assert controller.market_hours is not None


def test_timing_controller_customization(default_market_hours: MarketHours) -> None:
    """Custom configuration is preserved on the controller."""

    controller = TimingController(
        market_hours=default_market_hours,
        min_execution_delay_ms=100,
        max_execution_delay_ms=1000,
        allow_pre_post_market=True,
        require_regular_hours=True,
    )

    assert controller.min_execution_delay_ms == 100
    assert controller.max_execution_delay_ms == 1000
    assert controller.allow_pre_post_market is True
    assert controller.require_regular_hours is True
    assert controller.market_hours is default_market_hours


@pytest.mark.parametrize(
    (
        "controller_kwargs",
        "timestamp",
        "expected_valid",
        "reason_fragment",
        "expected_session",
    ),
    (
        pytest.param({}, dt_utc(2024, 1, 3, 10, 30), True, "Valid timing", MarketSession.REGULAR, id="regular-valid"),
        pytest.param({}, dt_utc(2024, 1, 6, 10, 30), False, "Market is closed", MarketSession.CLOSED, id="weekend-closed"),
        pytest.param(
            {"require_regular_hours": True},
            dt_utc(2024, 1, 3, 8, 0),
            False,
            "Regular market hours required",
            MarketSession.PRE_MARKET,
            id="pre-market-rejected",
        ),
        pytest.param(
            {"allow_pre_post_market": True},
            dt_utc(2024, 1, 3, 8, 0),
            True,
            "Valid timing",
            MarketSession.PRE_MARKET,
            id="pre-market-allowed",
        ),
        pytest.param(
            {"allow_pre_post_market": True},
            dt_utc(2024, 1, 3, 18, 0),
            True,
            "Valid timing",
            MarketSession.POST_MARKET,
            id="post-market-allowed",
        ),
    ),
)
def test_validate_timing(
    default_market_hours: MarketHours,
    controller_kwargs: dict,
    timestamp: datetime,
    expected_valid: bool,
    reason_fragment: str,
    expected_session: MarketSession,
) -> None:
    """Validation outcomes align with controller configuration."""

    controller = TimingController(market_hours=default_market_hours, **controller_kwargs)
    is_valid, reason, session = controller.validate_timing(timestamp)

    assert is_valid is expected_valid
    assert reason_fragment in reason
    assert session is expected_session


@pytest.mark.parametrize(
    ("quantity", "expected_min", "expected_max"),
    (
        pytest.param(100, 50, 150, id="small-order"),
        pytest.param(20_000, 250, None, id="large-order"),
    ),
)
def test_calculate_execution_delay_scaling(
    timing_controller: TimingController, quantity: int, expected_min: int, expected_max: int | None
) -> None:
    """Execution delay scales with order size within configured bounds."""

    timestamp = dt_utc(2024, 1, 3, 10, 30)
    delay = timing_controller.calculate_execution_delay(timestamp, quantity, MarketSession.REGULAR)

    assert delay >= expected_min
    if expected_max is not None:
        assert delay <= expected_max


def test_calculate_execution_delay_session_ordering(timing_controller: TimingController) -> None:
    """Session-specific delays respect the intended ordering."""

    timestamp = dt_utc(2024, 1, 3, 10, 30)
    regular_delay = timing_controller.calculate_execution_delay(timestamp, 100, MarketSession.REGULAR)
    pre_market_delay = timing_controller.calculate_execution_delay(timestamp, 100, MarketSession.PRE_MARKET)
    post_market_delay = timing_controller.calculate_execution_delay(timestamp, 100, MarketSession.POST_MARKET)

    assert pre_market_delay > regular_delay
    assert post_market_delay > pre_market_delay


def test_get_next_valid_execution_time(default_market_hours: MarketHours) -> None:
    """Controller locates the next permissible execution time."""

    controller = TimingController(market_hours=default_market_hours, require_regular_hours=True)
    timestamp = dt_utc(2024, 1, 6, 10, 0)

    next_valid = controller.get_next_valid_execution_time(timestamp, look_ahead_hours=72)

    assert next_valid is not None
    assert next_valid > timestamp
    is_valid, _, _ = controller.validate_timing(next_valid)
    assert is_valid


def test_get_next_valid_execution_time_none_found(default_market_hours: MarketHours) -> None:
    """A controller with impossible hours yields no valid execution time."""

    controller = TimingController(market_hours=default_market_hours, require_regular_hours=True)
    controller.market_hours = MarketHours(
        pre_market_start=time(23, 59),
        regular_start=time(23, 59),
        regular_end=time(23, 59),
        post_market_end=time(23, 59),
    )

    timestamp = dt_utc(2024, 1, 3, 10, 0)
    assert controller.get_next_valid_execution_time(timestamp, look_ahead_hours=1) is None


@pytest.mark.parametrize(
    ("samples", "expect_issues", "reason_fragment"),
    (
        pytest.param(
            (dt_utc(2024, 1, 3, 10, 0), dt_utc(2024, 1, 6, 10, 0)),
            True,
            "Market is closed",
            id="weekend-data",
        ),
        pytest.param(
            (dt_utc(2024, 1, 3, 10, 0), dt_utc(2024, 1, 3, 11, 0)),
            False,
            None,
            id="weekday-data",
        ),
        pytest.param((dt_utc(2024, 1, 3, 8, 0),), True, "Pre/post market trading not allowed", id="pre-market-data"),
    ),
)
def test_validate_backtest_timing(stream_strategy: Strategy, samples: tuple[datetime, ...], expect_issues: bool, reason_fragment: str | None) -> None:
    """Backtest timing validation surfaces issues for problematic data sets."""

    populate_stream(stream_strategy, samples)
    issues = validate_backtest_timing(stream_strategy)

    if not expect_issues:
        assert issues == {}
    else:
        assert issues
        assert reason_fragment is not None
        assert any(
            reason_fragment in issue["reason"]
            for node_issues in issues.values()
            for issue in node_issues
        )


def test_validate_backtest_timing_fail_on_invalid(stream_strategy: Strategy) -> None:
    """Validation raises when configured to fail on invalid samples."""

    populate_stream(stream_strategy, (dt_utc(2024, 1, 6, 10, 0),))

    with pytest.raises(ValueError, match="Invalid timing found"):
        validate_backtest_timing(stream_strategy, fail_on_invalid_timing=True)


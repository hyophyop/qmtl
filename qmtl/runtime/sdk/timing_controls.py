"""Enhanced timing controls for backtest execution accuracy."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MarketSession(str, Enum):
    """Market session types."""

    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    LUNCH = "lunch"
    POST_MARKET = "post_market"
    CLOSED = "closed"


@dataclass
class MarketHours:
    """Market hours configuration."""

    pre_market_start: time
    regular_start: time
    regular_end: time
    post_market_end: time
    lunch_start: Optional[time] = None
    lunch_end: Optional[time] = None
    early_closes: Optional[Dict[date, time]] = None
    timezone: str = "US/Eastern"

    def get_session(self, timestamp: datetime) -> MarketSession:
        """Determine market session for a given timestamp."""
        # Convert timestamp to market timezone
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Convert to market time (simplified - assumes US/Eastern)
        market_time = timestamp.time()

        regular_end = self.regular_end
        if self.early_closes and timestamp.date() in self.early_closes:
            regular_end = self.early_closes[timestamp.date()]

        # Check if it's a weekend (simplified)
        if timestamp.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return MarketSession.CLOSED

        if market_time < self.pre_market_start:
            return MarketSession.CLOSED
        elif market_time < self.regular_start:
            return MarketSession.PRE_MARKET
        elif market_time <= regular_end:
            if (
                self.lunch_start
                and self.lunch_end
                and self.lunch_start <= market_time < self.lunch_end
            ):
                return MarketSession.LUNCH
            return MarketSession.REGULAR
        elif market_time <= self.post_market_end:
            return MarketSession.POST_MARKET
        else:
            return MarketSession.CLOSED


class TimingController:
    """Controls timing aspects of trade execution."""

    def __init__(
        self,
        *,
        market_hours: Optional[MarketHours] = None,
        min_execution_delay_ms: int = 50,
        max_execution_delay_ms: int = 500,
        allow_pre_post_market: bool = False,
        require_regular_hours: bool = False,
    ):
        """Initialize timing controller.

        Parameters
        ----------
        market_hours : MarketHours, optional
            Market hours configuration. Defaults to US equity hours.
        min_execution_delay_ms : int
            Minimum execution delay in milliseconds.
        max_execution_delay_ms : int
            Maximum execution delay in milliseconds.
        allow_pre_post_market : bool
            Whether to allow trading in pre/post market hours.
        require_regular_hours : bool
            Whether to require regular market hours for execution.
        """
        self.market_hours = market_hours or MarketHours(
            pre_market_start=time(4, 0),  # 4:00 AM
            regular_start=time(9, 30),  # 9:30 AM
            regular_end=time(16, 0),  # 4:00 PM
            post_market_end=time(20, 0),  # 8:00 PM
        )
        self.min_execution_delay_ms = min_execution_delay_ms
        self.max_execution_delay_ms = max_execution_delay_ms
        self.allow_pre_post_market = allow_pre_post_market
        self.require_regular_hours = require_regular_hours

    def validate_timing(self, timestamp: datetime) -> Tuple[bool, str, MarketSession]:
        """Validate if execution is allowed at given timestamp.

        Returns
        -------
        Tuple[bool, str, MarketSession]
            (is_valid, reason, market_session)
        """
        session = self.market_hours.get_session(timestamp)

        if session in {MarketSession.CLOSED, MarketSession.LUNCH}:
            reason = "Market is closed"
            if session is MarketSession.LUNCH:
                reason = "Market closed for lunch"
            return False, reason, session

        if self.require_regular_hours and session != MarketSession.REGULAR:
            return False, "Regular market hours required", session

        if not self.allow_pre_post_market and session in [
            MarketSession.PRE_MARKET,
            MarketSession.POST_MARKET,
        ]:
            return False, "Pre/post market trading not allowed", session

        return True, "Valid timing", session

    def calculate_execution_delay(
        self,
        timestamp: datetime,
        order_size: float,
        market_session: MarketSession,
        base_delay_ms: Optional[int] = None,
    ) -> int:
        """Calculate realistic execution delay based on market conditions.

        Parameters
        ----------
        timestamp : datetime
            Order timestamp.
        order_size : float
            Size of the order.
        market_session : MarketSession
            Current market session.
        base_delay_ms : int, optional
            Base delay to add to. If None, uses min_execution_delay_ms.

        Returns
        -------
        int
            Execution delay in milliseconds.
        """
        if base_delay_ms is None:
            base_delay_ms = self.min_execution_delay_ms

        # Base delay
        delay = base_delay_ms

        # Add delay for market session
        if market_session == MarketSession.PRE_MARKET:
            delay += 100  # Higher latency in pre-market
        elif market_session == MarketSession.POST_MARKET:
            delay += 150  # Higher latency in post-market

        # Add delay based on order size (larger orders take longer)
        if order_size > 10000:
            delay += 200  # Large order penalty
        elif order_size > 1000:
            delay += 50  # Medium order penalty

        # Ensure within bounds
        delay = max(
            self.min_execution_delay_ms, min(delay, self.max_execution_delay_ms)
        )

        return delay

    def get_next_valid_execution_time(
        self, timestamp: datetime, look_ahead_hours: int = 24
    ) -> Optional[datetime]:
        """Find next valid execution time if current time is invalid.

        Parameters
        ----------
        timestamp : datetime
            Current timestamp.
        look_ahead_hours : int
            Hours to look ahead for valid execution time.

        Returns
        -------
        Optional[datetime]
            Next valid execution time, or None if none found.
        """
        from datetime import timedelta

        current = timestamp
        end_time = timestamp + timedelta(hours=look_ahead_hours)

        # Start by checking every 30 minutes for the first few hours,
        # then every hour to cover more ground
        increment = timedelta(minutes=30)

        while current <= end_time:
            is_valid, _, _ = self.validate_timing(current)
            if is_valid:
                return current

            current += increment

            # After 6 hours, switch to hourly increments
            if current > timestamp + timedelta(hours=6):
                increment = timedelta(hours=1)

        return None


def validate_backtest_timing(
    strategy,
    timing_controller: Optional[TimingController] = None,
    fail_on_invalid_timing: bool = False,
) -> dict[str, list]:
    """Validate timing of all data points in strategy for realistic execution.

    Parameters
    ----------
    strategy : Strategy
        Strategy instance with loaded data.
    timing_controller : TimingController, optional
        Timing controller for validation. Uses default if None.
    fail_on_invalid_timing : bool
        Whether to raise exception on invalid timing.

    Returns
    -------
    dict[str, list]
        Mapping from node name to list of invalid timing issues.

    Raises
    ------
    ValueError
        If fail_on_invalid_timing=True and invalid timing found.
    """
    from .node import StreamInput

    controller = timing_controller or TimingController()
    issues: dict[str, list] = {}

    for node in strategy.nodes:
        if not isinstance(node, StreamInput) or node.interval is None:
            continue

        node_issues = _collect_node_timing_issues(node, controller)
        if not node_issues:
            continue

        key = node.name or node.node_id
        issues[key] = node_issues

        if fail_on_invalid_timing:
            raise ValueError(
                f"Invalid timing found in node '{key}': "
                f"{len(node_issues)} issues detected"
            )

    return issues


def _iter_interval_samples(node, interval: int):
    """Yield (timestamp_ms, payload) for the given node interval."""
    cache_snapshot = node.cache._snapshot()
    for upstream_id, intervals in cache_snapshot.items():
        interval_data = intervals.get(interval)
        if not interval_data:
            continue
        for timestamp_ms, data in interval_data:
            yield timestamp_ms, data


def _collect_node_timing_issues(node, controller: "TimingController") -> list[dict]:
    """Collect timing issues for all samples of a single node."""
    node_issues: list[dict] = []

    for timestamp_ms, _ in _iter_interval_samples(node, node.interval):
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        is_valid, reason, session = controller.validate_timing(timestamp)
        if not is_valid:
            node_issues.append(
                {
                    "timestamp": timestamp_ms,
                    "reason": reason,
                    "session": session.value,
                    "datetime": timestamp.isoformat(),
                }
            )

    return node_issues

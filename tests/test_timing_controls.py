"""Tests for enhanced timing controls."""

import pytest
from datetime import datetime, time, timezone, timedelta
from qmtl.sdk.timing_controls import (
    TimingController, MarketHours, MarketSession, validate_backtest_timing
)


class TestMarketHours:
    """Test MarketHours functionality."""
    
    def test_regular_market_session(self):
        """Test identification of regular market hours."""
        market_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0)
        )
        
        # Regular market hours (10:30 AM on a Wednesday)
        timestamp = datetime(2024, 1, 3, 10, 30, tzinfo=timezone.utc)  # Wednesday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.REGULAR
    
    def test_pre_market_session(self):
        """Test identification of pre-market hours."""
        market_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0)
        )
        
        # Pre-market hours (8:00 AM on a Wednesday)
        timestamp = datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc)  # Wednesday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.PRE_MARKET
    
    def test_post_market_session(self):
        """Test identification of post-market hours."""
        market_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0)
        )
        
        # Post-market hours (18:00 / 6:00 PM on a Wednesday)
        timestamp = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)  # Wednesday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.POST_MARKET
    
    def test_closed_market_weekend(self):
        """Test identification of closed market during weekend."""
        market_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0)
        )
        
        # Saturday
        timestamp = datetime(2024, 1, 6, 10, 0, tzinfo=timezone.utc)  # Saturday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.CLOSED
        
        # Sunday
        timestamp = datetime(2024, 1, 7, 14, 0, tzinfo=timezone.utc)  # Sunday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.CLOSED
    
    def test_closed_market_hours(self):
        """Test identification of closed market during off hours."""
        market_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0)
        )
        
        # Very early morning (2:00 AM on a Wednesday)
        timestamp = datetime(2024, 1, 3, 2, 0, tzinfo=timezone.utc)  # Wednesday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.CLOSED
        
        # Late night (22:00 / 10:00 PM on a Wednesday)
        timestamp = datetime(2024, 1, 3, 22, 0, tzinfo=timezone.utc)  # Wednesday
        session = market_hours.get_session(timestamp)
        assert session == MarketSession.CLOSED


class TestTimingController:
    """Test TimingController functionality."""
    
    def test_default_initialization(self):
        """Test default initialization of TimingController."""
        controller = TimingController()
        
        assert controller.min_execution_delay_ms == 50
        assert controller.max_execution_delay_ms == 500
        assert not controller.allow_pre_post_market
        assert not controller.require_regular_hours
        assert controller.market_hours is not None
    
    def test_custom_initialization(self):
        """Test custom initialization of TimingController."""
        market_hours = MarketHours(
            pre_market_start=time(5, 0),
            regular_start=time(10, 0),
            regular_end=time(15, 0),
            post_market_end=time(19, 0)
        )
        
        controller = TimingController(
            market_hours=market_hours,
            min_execution_delay_ms=100,
            max_execution_delay_ms=1000,
            allow_pre_post_market=True,
            require_regular_hours=True
        )
        
        assert controller.min_execution_delay_ms == 100
        assert controller.max_execution_delay_ms == 1000
        assert controller.allow_pre_post_market
        assert controller.require_regular_hours
        assert controller.market_hours == market_hours
    
    def test_validate_timing_regular_hours(self):
        """Test timing validation during regular hours."""
        controller = TimingController()
        
        # Regular market hours (Wednesday 10:30 AM)
        timestamp = datetime(2024, 1, 3, 10, 30, tzinfo=timezone.utc)
        is_valid, reason, session = controller.validate_timing(timestamp)
        
        assert is_valid
        assert "Valid timing" in reason
        assert session == MarketSession.REGULAR
    
    def test_validate_timing_closed_market(self):
        """Test timing validation when market is closed."""
        controller = TimingController()
        
        # Market closed (Saturday)
        timestamp = datetime(2024, 1, 6, 10, 30, tzinfo=timezone.utc)
        is_valid, reason, session = controller.validate_timing(timestamp)
        
        assert not is_valid
        assert "Market is closed" in reason
        assert session == MarketSession.CLOSED
    
    def test_validate_timing_require_regular_hours(self):
        """Test timing validation with required regular hours."""
        controller = TimingController(require_regular_hours=True)
        
        # Pre-market (Wednesday 8:00 AM)
        timestamp = datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc)
        is_valid, reason, session = controller.validate_timing(timestamp)
        
        assert not is_valid
        assert "Regular market hours required" in reason
        assert session == MarketSession.PRE_MARKET
    
    def test_validate_timing_allow_pre_post_market(self):
        """Test timing validation with pre/post market allowed."""
        controller = TimingController(allow_pre_post_market=True)
        
        # Pre-market (Wednesday 8:00 AM)
        timestamp = datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc)
        is_valid, reason, session = controller.validate_timing(timestamp)
        
        assert is_valid
        assert "Valid timing" in reason
        assert session == MarketSession.PRE_MARKET
        
        # Post-market (Wednesday 6:00 PM)
        timestamp = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)
        is_valid, reason, session = controller.validate_timing(timestamp)
        
        assert is_valid
        assert "Valid timing" in reason
        assert session == MarketSession.POST_MARKET
    
    def test_calculate_execution_delay_regular_hours(self):
        """Test execution delay calculation during regular hours."""
        controller = TimingController(
            min_execution_delay_ms=50,
            max_execution_delay_ms=500
        )
        
        timestamp = datetime(2024, 1, 3, 10, 30, tzinfo=timezone.utc)
        
        # Small order
        delay = controller.calculate_execution_delay(
            timestamp, 100, MarketSession.REGULAR
        )
        assert 50 <= delay <= 150  # Base delay + small order
        
        # Large order
        delay = controller.calculate_execution_delay(
            timestamp, 20000, MarketSession.REGULAR
        )
        assert delay >= 250  # Base delay + large order penalty
    
    def test_calculate_execution_delay_pre_post_market(self):
        """Test execution delay calculation in pre/post market."""
        controller = TimingController()
        
        timestamp = datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc)
        
        # Pre-market should have higher delay
        pre_delay = controller.calculate_execution_delay(
            timestamp, 100, MarketSession.PRE_MARKET
        )
        
        regular_delay = controller.calculate_execution_delay(
            timestamp, 100, MarketSession.REGULAR
        )
        
        assert pre_delay > regular_delay
        
        # Post-market should have even higher delay
        post_delay = controller.calculate_execution_delay(
            timestamp, 100, MarketSession.POST_MARKET
        )
        
        assert post_delay > pre_delay
    
    def test_get_next_valid_execution_time(self):
        """Test finding next valid execution time."""
        controller = TimingController(require_regular_hours=True)
        
        # Saturday (market closed)
        timestamp = datetime(2024, 1, 6, 10, 0, tzinfo=timezone.utc)  # Saturday
        
        next_valid = controller.get_next_valid_execution_time(timestamp, look_ahead_hours=72)  # Look 3 days ahead
        
        # Should find a valid time (likely Monday)
        assert next_valid is not None
        assert next_valid > timestamp
        
        # Validate that the returned time is actually valid
        is_valid, _, _ = controller.validate_timing(next_valid)
        assert is_valid
    
    def test_get_next_valid_execution_time_none_found(self):
        """Test when no valid execution time is found."""
        # Controller that never allows execution
        controller = TimingController(require_regular_hours=True)
        controller.market_hours = MarketHours(
            pre_market_start=time(23, 59),  # Impossible hours
            regular_start=time(23, 59),
            regular_end=time(23, 59),
            post_market_end=time(23, 59)
        )
        
        timestamp = datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc)
        
        next_valid = controller.get_next_valid_execution_time(
            timestamp, look_ahead_hours=1  # Short look-ahead
        )
        
        assert next_valid is None


def test_validate_backtest_timing_integration():
    """Test integration of timing validation with strategy."""
    from qmtl.sdk import Strategy, StreamInput
    
    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="3600s", period=10)  # 1 hour intervals
            self.add_nodes([stream])
    
    strategy = TestStrategy()
    strategy.setup()
    
    # Add test data with some weekend timestamps
    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            # Add weekday data (should be valid)
            weekday_ts = int(datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 3600, weekday_ts, {"close": 100.0})
            
            # Add weekend data (should be invalid)
            weekend_ts = int(datetime(2024, 1, 6, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 3600, weekend_ts, {"close": 101.0})
    
    # Test with default controller (should find issues)
    issues = validate_backtest_timing(strategy)
    
    # Should have issues for weekend data
    assert len(issues) >= 1
    
    for node_name, node_issues in issues.items():
        assert len(node_issues) >= 1
        assert any("Market is closed" in issue["reason"] for issue in node_issues)


def test_validate_backtest_timing_fail_on_invalid():
    """Test that validation raises exception when configured to fail."""
    from qmtl.sdk import Strategy, StreamInput
    
    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="3600s", period=10)
            self.add_nodes([stream])
    
    strategy = TestStrategy()
    strategy.setup()
    
    # Add weekend data (invalid timing)
    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            weekend_ts = int(datetime(2024, 1, 6, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 3600, weekend_ts, {"close": 100.0})
    
    # Should raise ValueError with fail_on_invalid_timing=True
    with pytest.raises(ValueError, match="Invalid timing found"):
        validate_backtest_timing(strategy, fail_on_invalid_timing=True)


def test_validate_backtest_timing_clean_data():
    """Test validation with clean weekday data."""
    from qmtl.sdk import Strategy, StreamInput
    
    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="3600s", period=10)
            self.add_nodes([stream])
    
    strategy = TestStrategy()
    strategy.setup()
    
    # Add only weekday data (should be valid)
    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            # Wednesday 10:00 AM
            weekday_ts = int(datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 3600, weekday_ts, {"close": 100.0})
            
            # Wednesday 11:00 AM
            weekday_ts2 = int(datetime(2024, 1, 3, 11, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 3600, weekday_ts2, {"close": 101.0})
    
    # Should have no issues
    issues = validate_backtest_timing(strategy)
    assert len(issues) == 0


def test_validate_backtest_timing_flags_pre_market():
    """Ensure pre-market data is reported as invalid."""
    from qmtl.sdk import Strategy, StreamInput

    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="3600s", period=10)
            self.add_nodes([stream])

    strategy = TestStrategy()
    strategy.setup()

    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            pre_market_ts = int(
                datetime(2024, 1, 3, 8, 0, tzinfo=timezone.utc).timestamp() * 1000
            )
            node.cache.append("test_queue", 3600, pre_market_ts, {"close": 100.0})

    issues = validate_backtest_timing(strategy)

    assert len(issues) >= 1
    for node_name, node_issues in issues.items():
        assert any(
            "Pre/post market trading not allowed" in issue["reason"]
            for issue in node_issues
        )

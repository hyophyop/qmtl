"""Tests for enhanced backtest data validation."""

import pytest
import polars as pl
from qmtl.runtime.sdk.backtest_validation import BacktestDataValidator, DataQualityReport, validate_backtest_data
from qmtl.runtime.sdk import Strategy, StreamInput, Node


class TestBacktestDataValidator:
    """Test enhanced backtest data validation."""
    
    def test_validator_initialization(self):
        """Test validator can be initialized with custom parameters."""
        validator = BacktestDataValidator(
            max_price_change_pct=0.05,
            min_price=0.01,
            max_gap_tolerance_sec=60,
            required_fields=["open", "high", "low", "close"]
        )
        assert validator.max_price_change_pct == 0.05
        assert validator.min_price == 0.01
        assert validator.max_gap_tolerance_sec == 60
        assert validator.required_fields == ["open", "high", "low", "close"]
    
    def test_validate_clean_data(self):
        """Test validation of clean, good quality data."""
        validator = BacktestDataValidator()
        
        # Create clean test data
        data = [
            (100, {"close": 10.0, "volume": 1000}),
            (160, {"close": 10.1, "volume": 1200}),
            (220, {"close": 10.05, "volume": 800}),
            (280, {"close": 10.2, "volume": 1500}),
        ]
        
        report = validator.validate_time_series(data, interval_sec=60)
        
        assert report.total_records == 4
        assert report.valid_records == 4
        assert report.data_quality_score == 1.0
        assert not report.has_issues
        assert len(report.timestamp_gaps) == 0
        assert len(report.invalid_prices) == 0
        assert len(report.suspicious_moves) == 0
        assert len(report.missing_fields) == 0
    
    def test_detect_timestamp_gaps(self):
        """Test detection of timestamp gaps."""
        validator = BacktestDataValidator(max_gap_tolerance_sec=30)
        
        # Create data with gaps
        data = [
            (100, {"close": 10.0}),
            (160, {"close": 10.1}),  # 60s gap - OK
            (300, {"close": 10.05}), # 140s gap - too large
            (360, {"close": 10.2}),  # 60s gap - OK
        ]
        
        report = validator.validate_time_series(data, interval_sec=60)
        
        assert len(report.timestamp_gaps) == 1
        assert report.timestamp_gaps[0] == (160, 300)
    
    def test_detect_invalid_prices(self):
        """Test detection of invalid price values."""
        validator = BacktestDataValidator(min_price=1.0)
        
        # Create data with invalid prices
        data = [
            (100, {"close": 10.0}),
            (160, {"close": -5.0}),    # Negative price
            (220, {"close": 0.5}),     # Below minimum
            (280, {"close": float('nan')}),  # NaN
            (340, {"close": float('inf')}),  # Infinity
        ]
        
        report = validator.validate_time_series(data, interval_sec=60)
        
        assert len(report.invalid_prices) >= 3  # At least negative, below min, NaN, inf
        assert report.valid_records < report.total_records
    
    def test_detect_suspicious_moves(self):
        """Test detection of suspicious price movements."""
        validator = BacktestDataValidator(max_price_change_pct=0.05)  # 5% max change
        
        # Create data with large price movements
        data = [
            (100, {"close": 10.0}),
            (160, {"close": 12.0}),   # 20% increase - suspicious
            (220, {"close": 11.0}),   # 8.3% decrease - suspicious  
            (280, {"close": 11.05}),  # 0.45% increase - OK
        ]
        
        report = validator.validate_time_series(data, interval_sec=60)
        
        assert len(report.suspicious_moves) >= 2
        assert any("20.0%" in move[2] or "0.2" in str(move[1]) for move in report.suspicious_moves)
    
    def test_detect_missing_fields(self):
        """Test detection of missing required fields."""
        validator = BacktestDataValidator(required_fields=["open", "high", "low", "close"])
        
        # Create data with missing fields
        data = [
            (100, {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.1}),  # Complete
            (160, {"high": 10.5, "low": 10.0, "close": 10.3}),               # Missing open
            (220, {"open": 10.3, "close": 10.2}),                           # Missing high, low
            (280, {}),                                                       # Missing all
        ]
        
        report = validator.validate_time_series(data, interval_sec=60)
        
        assert len(report.missing_fields) >= 4  # open, high, low from different records
        assert report.valid_records == 1  # Only first record is complete
    
    def test_validate_ohlc_relationships(self):
        """Test validation of OHLC price relationships."""
        validator = BacktestDataValidator()
        
        # Create data with invalid OHLC relationships
        data = [
            (100, {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.1}),  # Valid
            (160, {"open": 10.0, "high": 9.8, "low": 10.2, "close": 10.1}),  # High < Low  
            (220, {"open": 10.5, "high": 10.2, "low": 9.8, "close": 10.1}),  # Open > High
            (280, {"open": 10.0, "high": 10.2, "low": 9.8, "close": 10.5}),  # Close > High
        ]
        
        report = validator.validate_time_series(data, interval_sec=60)
        
        # Should detect invalid OHLC relationships
        assert len(report.invalid_prices) >= 3
        assert any("Invalid OHLC" in price[1] for price in report.invalid_prices)
    
    def test_data_quality_score_calculation(self):
        """Test data quality score calculation."""
        # Empty data
        report = DataQualityReport([], [], [], [], 0, 0)
        assert report.data_quality_score == 0.0
        
        # Perfect data
        report = DataQualityReport([], [], [], [], 10, 10)
        assert report.data_quality_score == 1.0
        
        # 80% quality
        report = DataQualityReport([], [], [], [], 10, 8)
        assert report.data_quality_score == 0.8
    
    def test_has_issues_property(self):
        """Test has_issues property correctly identifies problems."""
        # No issues
        report = DataQualityReport([], [], [], [], 10, 10)
        assert not report.has_issues
        
        # Has timestamp gaps
        report = DataQualityReport([(100, 200)], [], [], [], 10, 10)
        assert report.has_issues
        
        # Has invalid prices
        report = DataQualityReport([], [(100, "negative price")], [], [], 10, 9)
        assert report.has_issues
        
        # Has suspicious moves
        report = DataQualityReport([], [], [(100, 0.5, "large change")], [], 10, 10)
        assert report.has_issues
        
        # Has missing fields
        report = DataQualityReport([], [], [], [(100, "close")], 10, 9)
        assert report.has_issues


def test_validate_backtest_data_integration():
    """Test integration with strategy validation."""
    
    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(
                interval="60s", 
                period=10
            )
            stream.name = "test_stream"  # Set name after creation
            self.add_nodes([stream])
    
    strategy = TestStrategy()
    strategy.setup()  # Explicitly call setup
    
    # Add data directly to the cache
    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            # Add test data directly to cache
            node.cache.append("test_queue", 60, 60, {"close": 10.0, "volume": 1000})
            node.cache.append("test_queue", 60, 120, {"close": 10.1, "volume": 1200})
    
    # Test validation
    reports = validate_backtest_data(strategy)
    
    # Should have at least one report
    assert len(reports) >= 1
    
    # All reports should have good quality for clean test data
    for node_name, report in reports.items():
        assert report.data_quality_score >= 0.8  # At least 80% quality


def test_validate_backtest_data_quality_threshold():
    """Test that low quality data raises an error."""
    
    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(
                interval="60s", 
                period=10
            )
            stream.name = "test_stream"  # Set name after creation
            self.add_nodes([stream])
    
    strategy = TestStrategy()
    strategy.setup()  # Explicitly call setup
    
    # Add bad data directly to cache
    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            # Add bad data that should fail validation
            node.cache.append("test_queue", 60, 60, {"close": -10.0})  # Bad negative price
            node.cache.append("test_queue", 60, 120, {"close": float('nan')})  # Bad NaN price
    
    # Should raise ValueError due to low quality
    with pytest.raises(ValueError, match="Data quality.*below required threshold"):
        validate_backtest_data(strategy, fail_on_quality_threshold=0.8)
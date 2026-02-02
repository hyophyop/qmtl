"""Tests for Tick and Quote conformance rules."""

import pytest
import polars as pl

from qmtl.runtime.sdk.conformance import (
    TickConformanceRule,
    QuoteConformanceRule,
    ConformanceReport,
)


class TestTickConformanceRule:
    """Test TickConformanceRule validation."""
    
    def test_valid_tick_data(self):
        """Valid tick data passes without warnings."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000001, 1700000002],
            'price': [100.0, 100.5, 101.0],
            'size': [1.0, 2.0, 1.5],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert len(report.warnings) == 0
        assert len(report.flags_counts) == 0
    
    def test_missing_columns(self):
        """Missing required columns triggers warning."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'price': [100.0],
            # missing 'size'
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert len(report.warnings) > 0
        assert any('Missing required columns' in w for w in report.warnings)
        assert 'missing_column' in report.flags_counts
    
    def test_non_positive_price(self):
        """Non-positive prices trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000001],
            'price': [100.0, -50.0],
            'size': [1.0, 2.0],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert any('Non-positive prices' in w for w in report.warnings)
        assert 'invalid_price' in report.flags_counts
    
    def test_non_positive_size(self):
        """Non-positive sizes trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000001],
            'price': [100.0, 100.5],
            'size': [1.0, 0.0],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert any('Non-positive sizes' in w for w in report.warnings)
        assert 'invalid_size' in report.flags_counts
    
    def test_unsorted_timestamps(self):
        """Unsorted timestamps trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000002, 1700000001, 1700000000],
            'price': [100.0, 100.5, 101.0],
            'size': [1.0, 2.0, 1.5],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert any('not sorted' in w for w in report.warnings)
        assert 'unsorted_ts' in report.flags_counts
    
    def test_duplicate_timestamps(self):
        """Duplicate timestamps trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000000, 1700000001],
            'price': [100.0, 100.5, 101.0],
            'size': [1.0, 2.0, 1.5],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert any('Duplicate timestamps' in w for w in report.warnings)
        assert 'duplicate_ts' in report.flags_counts
    
    def test_invalid_timestamp_range(self):
        """Invalid timestamp range triggers warning."""
        df = pl.DataFrame({
            'ts': [-100, 1700000001],
            'price': [100.0, 100.5],
            'size': [1.0, 2.0],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert any('Invalid timestamp range' in w for w in report.warnings)
        assert 'invalid_timestamp' in report.flags_counts
    
    def test_nan_values(self):
        """NaN values trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000001],
            'price': [100.0, float('nan')],
            'size': [1.0, 2.0],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        assert any('NaN values' in w for w in report.warnings)
        assert 'nan_price' in report.flags_counts


class TestQuoteConformanceRule:
    """Test QuoteConformanceRule validation."""
    
    def test_valid_quote_data(self):
        """Valid quote data passes without warnings."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000001],
            'bid': [100.0, 100.5],
            'ask': [100.5, 101.0],
            'bid_size': [10.0, 12.0],
            'ask_size': [8.0, 9.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert len(report.warnings) == 0
        assert len(report.flags_counts) == 0
    
    def test_missing_columns(self):
        """Missing required columns triggers warning."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'bid': [100.0],
            'ask': [100.5],
            # missing bid_size, ask_size
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert len(report.warnings) > 0
        assert any('Missing required columns' in w for w in report.warnings)
        assert 'missing_column' in report.flags_counts
    
    def test_crossed_quotes(self):
        """Crossed quotes (bid >= ask) trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000, 1700000001],
            'bid': [100.0, 101.0],
            'ask': [100.5, 100.5],  # Crossed on second row
            'bid_size': [10.0, 12.0],
            'ask_size': [8.0, 9.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert any('Crossed quotes' in w for w in report.warnings)
        assert 'crossed_quotes' in report.flags_counts
    
    def test_non_positive_bid(self):
        """Non-positive bid prices trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'bid': [0.0],
            'ask': [100.5],
            'bid_size': [10.0],
            'ask_size': [8.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert any('Non-positive bid' in w for w in report.warnings)
        assert 'invalid_bid' in report.flags_counts
    
    def test_non_positive_sizes(self):
        """Non-positive sizes trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'bid': [100.0],
            'ask': [100.5],
            'bid_size': [0.0],
            'ask_size': [8.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert any('Non-positive bid_size' in w for w in report.warnings)
        assert 'invalid_bid_size' in report.flags_counts
    
    def test_wide_spreads(self):
        """Wide spreads (>10%) trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'bid': [100.0],
            'ask': [120.0],  # 20% spread
            'bid_size': [10.0],
            'ask_size': [8.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert any('Wide spreads' in w for w in report.warnings)
        assert 'wide_spread' in report.flags_counts
    
    def test_unsorted_timestamps(self):
        """Unsorted timestamps trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000001, 1700000000],
            'bid': [100.0, 100.5],
            'ask': [100.5, 101.0],
            'bid_size': [10.0, 12.0],
            'ask_size': [8.0, 9.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert any('not sorted' in w for w in report.warnings)
        assert 'unsorted_ts' in report.flags_counts
    
    def test_nan_values(self):
        """NaN values trigger warning."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'bid': [float('nan')],
            'ask': [100.5],
            'bid_size': [10.0],
            'ask_size': [8.0],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert any('NaN values' in w for w in report.warnings)
        assert 'nan_bid' in report.flags_counts


class TestConformanceRulesIntegration:
    """Integration tests for conformance rules."""
    
    def test_tick_rule_with_optional_columns(self):
        """Tick rule accepts optional columns."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'price': [100.0],
            'size': [1.0],
            'side': ['buy'],
            'trade_id': [12345],
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        # Should pass without warnings
        assert len(report.warnings) == 0
    
    def test_quote_rule_with_optional_columns(self):
        """Quote rule accepts optional columns."""
        df = pl.DataFrame({
            'ts': [1700000000],
            'bid': [100.0],
            'ask': [100.5],
            'bid_size': [10.0],
            'ask_size': [8.0],
            'quote_id': [67890],
            'venue_ts': [1700000000],
        })
        
        rule = QuoteConformanceRule()
        report = rule.validate(df)
        
        assert len(report.warnings) == 0
    
    def test_multiple_validation_issues(self):
        """Multiple issues are all reported."""
        df = pl.DataFrame({
            'ts': [1700000001, 1700000000],  # Unsorted
            'price': [100.0, -50.0],  # Negative price
            'size': [1.0, 0.0],  # Zero size
        })
        
        rule = TickConformanceRule()
        report = rule.validate(df)
        
        # Should have multiple warnings
        assert len(report.warnings) >= 3
        assert len(report.flags_counts) >= 3

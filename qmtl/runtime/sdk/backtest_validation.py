"""Enhanced validation for backtest execution accuracy."""

from __future__ import annotations

import logging
import math
import statistics
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DataQualityReport:
    """Report on data quality issues found during validation."""
    
    timestamp_gaps: List[Tuple[int, int]]  # (start, end) of gaps
    invalid_prices: List[Tuple[int, str]]  # (timestamp, reason)
    suspicious_moves: List[Tuple[int, float, str]]  # (timestamp, change, reason)
    missing_fields: List[Tuple[int, str]]  # (timestamp, field_name)
    total_records: int
    valid_records: int
    
    @property
    def data_quality_score(self) -> float:
        """Calculate overall data quality score (0-1)."""
        if self.total_records == 0:
            return 0.0
        return self.valid_records / self.total_records
    
    @property
    def has_issues(self) -> bool:
        """Check if any data quality issues were found."""
        return bool(
            self.timestamp_gaps or 
            self.invalid_prices or 
            self.suspicious_moves or 
            self.missing_fields
        )


class BacktestDataValidator:
    """Validates data quality before backtest execution."""
    
    def __init__(
        self, 
        *,
        max_price_change_pct: float = 0.1,  # 10% max single-period change
        min_price: float = 0.001,
        max_gap_tolerance_sec: int = 300,  # 5 minutes
        required_fields: Optional[List[str]] = None,
    ):
        """Initialize validator with configurable thresholds.
        
        Parameters
        ----------
        max_price_change_pct : float
            Maximum allowed single-period price change (as fraction).
        min_price : float  
            Minimum allowed price value.
        max_gap_tolerance_sec : int
            Maximum allowed gap in seconds between data points.
        required_fields : List[str], optional
            List of required fields in each data record.
        """
        self.max_price_change_pct = max_price_change_pct
        self.min_price = min_price
        self.max_gap_tolerance_sec = max_gap_tolerance_sec
        self.required_fields = required_fields or ["close"]
    
    def validate_time_series(
        self, 
        data: List[Tuple[int, Dict[str, Any]]],
        interval_sec: int,
    ) -> DataQualityReport:
        """Validate a time series for data quality issues.
        
        Parameters
        ----------
        data : List[Tuple[int, Dict[str, Any]]]
            List of (timestamp, data_dict) tuples.
        interval_sec : int
            Expected interval between data points in seconds.
            
        Returns
        -------
        DataQualityReport
            Report containing all identified data quality issues.
        """
        if not data:
            return DataQualityReport([], [], [], [], 0, 0)
            
        report = DataQualityReport([], [], [], [], len(data), 0)
        
        # Sort data by timestamp
        sorted_data = sorted(data, key=lambda x: x[0])
        
        # Check for timestamp gaps
        report.timestamp_gaps = self._check_timestamp_gaps(sorted_data, interval_sec)
        
        # Validate individual records
        valid_count = 0
        prev_prices = {}
        
        for i, (timestamp, record) in enumerate(sorted_data):
            is_valid = True
            
            # Check for missing required fields
            for field in self.required_fields:
                if field not in record or record[field] is None:
                    report.missing_fields.append((timestamp, field))
                    is_valid = False
            
            # Validate price fields
            price_fields = [f for f in record.keys() if f in ['open', 'high', 'low', 'close', 'price']]
            for field in price_fields:
                if field in record and record[field] is not None:
                    price = record[field]
                    
                    # Check for invalid price values
                    if not isinstance(price, (int, float)) or math.isnan(price) or math.isinf(price):
                        report.invalid_prices.append((timestamp, f"{field}: not a valid number"))
                        is_valid = False
                        continue
                        
                    if price < self.min_price:
                        report.invalid_prices.append((timestamp, f"{field}: price {price} below minimum {self.min_price}"))
                        is_valid = False
                        continue
                    
                    # Check for suspicious price movements
                    if field in prev_prices and prev_prices[field] is not None:
                        change = abs(price - prev_prices[field]) / prev_prices[field]
                        if change > self.max_price_change_pct:
                            report.suspicious_moves.append((
                                timestamp, 
                                change, 
                                f"{field}: {change:.1%} change from {prev_prices[field]} to {price}"
                            ))
                    
                    prev_prices[field] = price
            
            # Validate OHLC relationships if all present
            if all(f in record and record[f] is not None for f in ['open', 'high', 'low', 'close']):
                o, h, l, c = record['open'], record['high'], record['low'], record['close']
                if not (l <= o <= h and l <= c <= h):
                    report.invalid_prices.append((timestamp, f"Invalid OHLC: O={o}, H={h}, L={l}, C={c}"))
                    is_valid = False
            
            if is_valid:
                valid_count += 1
        
        report.valid_records = valid_count
        return report
    
    def _check_timestamp_gaps(
        self, 
        sorted_data: List[Tuple[int, Dict[str, Any]]], 
        interval_sec: int
    ) -> List[Tuple[int, int]]:
        """Check for gaps in timestamp sequence."""
        gaps = []
        
        for i in range(1, len(sorted_data)):
            prev_ts = sorted_data[i-1][0]
            curr_ts = sorted_data[i][0]
            gap = curr_ts - prev_ts
            
            # Expected gap should be close to interval_sec
            if gap > interval_sec + self.max_gap_tolerance_sec:
                gaps.append((prev_ts, curr_ts))
        
        return gaps
    
    def log_validation_results(self, report: DataQualityReport, node_name: str = "unknown") -> None:
        """Log validation results for debugging."""
        logger.info(f"Data validation for {node_name}: {report.valid_records}/{report.total_records} valid records "
                   f"(quality score: {report.data_quality_score:.2%})")
        
        if report.timestamp_gaps:
            logger.warning(f"Found {len(report.timestamp_gaps)} timestamp gaps in {node_name}")
            
        if report.invalid_prices:
            logger.warning(f"Found {len(report.invalid_prices)} invalid prices in {node_name}")
            for ts, reason in report.invalid_prices[:5]:  # Log first 5 issues
                logger.warning(f"  {ts}: {reason}")
                
        if report.suspicious_moves:
            logger.warning(f"Found {len(report.suspicious_moves)} suspicious price movements in {node_name}")
            for ts, change, reason in report.suspicious_moves[:5]:  # Log first 5 issues
                logger.warning(f"  {ts}: {reason}")
                
        if report.missing_fields:
            logger.warning(f"Found {len(report.missing_fields)} missing required fields in {node_name}")


def validate_backtest_data(
    strategy,
    *,
    validation_config: Optional[Dict[str, Any]] = None,
    fail_on_quality_threshold: float = 0.8,
) -> Dict[str, DataQualityReport]:
    """Validate all data in strategy nodes before backtest execution.
    
    Parameters
    ----------
    strategy : Strategy
        Strategy instance with loaded data.
    validation_config : Dict[str, Any], optional
        Configuration for data validation thresholds.
    fail_on_quality_threshold : float
        Minimum data quality score required (0-1). Raises ValueError if any node falls below this.
        
    Returns
    -------
    Dict[str, DataQualityReport]
        Mapping from node name to data quality report.
        
    Raises
    ------
    ValueError
        If any node's data quality falls below the threshold.
    """
    from .node import StreamInput
    
    config = validation_config or {}
    validator = BacktestDataValidator(**config)
    reports = {}
    
    for node in strategy.nodes:
        if isinstance(node, StreamInput) and node.interval is not None:
            # Get all cached data for this node
            all_data = []
            
            # Get snapshot of cache data
            cache_snapshot = node.cache._snapshot()
            
            for upstream_id, intervals in cache_snapshot.items():
                if node.interval in intervals:
                    interval_data = intervals[node.interval]
                    all_data.extend(interval_data)
            
            if all_data:
                # Validate the time series
                report = validator.validate_time_series(all_data, node.interval)
                reports[node.name or node.node_id] = report
                
                # Log results
                validator.log_validation_results(report, node.name or node.node_id)
                
                # Check quality threshold
                if report.data_quality_score < fail_on_quality_threshold:
                    raise ValueError(
                        f"Data quality for node '{node.name or node.node_id}' is {report.data_quality_score:.2%}, "
                        f"below required threshold of {fail_on_quality_threshold:.2%}"
                    )
    
    return reports
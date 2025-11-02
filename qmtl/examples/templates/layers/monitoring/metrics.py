"""Basic metrics collection.

This module provides simple metrics collection for strategy monitoring.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and records strategy metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.metrics: Dict[str, Any] = {}

    def record_signal(self, signal: str, strength: float, timestamp: Any = None):
        """Record a trading signal.

        Args:
            signal: Signal type (BUY, SELL, HOLD)
            strength: Signal strength (0-1)
            timestamp: Signal timestamp
        """
        logger.info(f"Signal: {signal}, Strength: {strength:.2f}, Time: {timestamp}")
        
        if "signals" not in self.metrics:
            self.metrics["signals"] = []
        
        self.metrics["signals"].append({
            "signal": signal,
            "strength": strength,
            "timestamp": timestamp,
        })

    def record_trade(self, symbol: str, side: str, amount: float, price: float):
        """Record a trade execution.

        Args:
            symbol: Trading symbol
            side: Trade side (buy/sell)
            amount: Trade amount
            price: Execution price
        """
        logger.info(f"Trade: {side} {amount} {symbol} @ {price}")
        
        if "trades" not in self.metrics:
            self.metrics["trades"] = []
        
        self.metrics["trades"].append({
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
        })

    def record_performance(self, metric_name: str, value: float):
        """Record a performance metric.

        Args:
            metric_name: Name of the metric
            value: Metric value
        """
        logger.info(f"Performance {metric_name}: {value:.4f}")
        
        if "performance" not in self.metrics:
            self.metrics["performance"] = {}
        
        self.metrics["performance"][metric_name] = value

    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics.

        Returns:
            Dictionary of all metrics
        """
        return self.metrics

    def reset(self):
        """Reset all metrics."""
        self.metrics = {}


# Global metrics collector instance
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return _metrics_collector

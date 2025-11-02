"""Single indicator signal generation strategy.

This module demonstrates a simple strategy using a single technical indicator.
"""

from __future__ import annotations

from qmtl.runtime.sdk import Strategy, Node
from qmtl.runtime.indicators import ema


class SingleIndicatorStrategy(Strategy):
    """Simple EMA-based strategy."""

    def __init__(self):
        super().__init__(default_interval="60s", default_period=30)

    def setup(self):
        """Setup strategy nodes."""
        # Import data provider from data layer
        from layers.data.providers import get_data_provider
        
        price_stream = get_data_provider()
        
        # Calculate EMA
        ema_node = ema(price_stream, period=20, name="ema_20")
        
        # Generate signal
        def generate_signal(view):
            """Compare price with EMA to generate signal."""
            price_data = view[price_stream][price_stream.interval]
            ema_data = view[ema_node][ema_node.interval]
            
            if not price_data or not ema_data:
                return {"signal": "HOLD", "strength": 0}
            
            price = price_data[-1][1]["close"]
            ema = ema_data[-1][1]
            
            if price > ema:
                return {"signal": "BUY", "strength": 1}
            elif price < ema:
                return {"signal": "SELL", "strength": 1}
            else:
                return {"signal": "HOLD", "strength": 0}
        
        signal_node = Node(
            input=ema_node,
            compute_fn=generate_signal,
            name="signal",
        )
        
        self.add_nodes([price_stream, ema_node, signal_node])


def create_strategy() -> Strategy:
    """Create and return the strategy instance."""
    return SingleIndicatorStrategy()

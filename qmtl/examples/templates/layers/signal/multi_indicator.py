"""Multiple indicator signal generation strategy.

This module combines multiple technical indicators for signal generation.
"""

from __future__ import annotations

from qmtl.runtime.sdk import Strategy, Node
from qmtl.runtime.indicators import ema, rsi


class MultiIndicatorStrategy(Strategy):
    """Strategy combining EMA and RSI."""

    def __init__(self):
        super().__init__(default_interval="60s", default_period=50)

    def setup(self):
        """Setup strategy nodes."""
        # Import data provider from data layer
        from qmtl.examples.templates.layers.data.providers import get_data_provider
        
        price_stream = get_data_provider()
        
        # Calculate indicators
        ema_short = ema(price_stream, period=10, name="ema_10")
        ema_long = ema(price_stream, period=30, name="ema_30")
        rsi_node = rsi(price_stream, period=14, name="rsi_14")
        
        # Combine indicators for signal
        def generate_signal(view):
            """Combine EMA crossover and RSI for signal."""
            ema_s = view[ema_short][ema_short.interval]
            ema_l = view[ema_long][ema_long.interval]
            rsi_data = view[rsi_node][rsi_node.interval]
            
            if not ema_s or not ema_l or not rsi_data:
                return {"signal": "HOLD", "strength": 0}
            
            ema_s_val = ema_s[-1][1]
            ema_l_val = ema_l[-1][1]
            rsi_val = rsi_data[-1][1]
            
            # EMA crossover + RSI confirmation
            if ema_s_val > ema_l_val and rsi_val < 70:
                strength = min((ema_s_val - ema_l_val) / ema_l_val * 100, 1.0)
                return {"signal": "BUY", "strength": strength}
            elif ema_s_val < ema_l_val and rsi_val > 30:
                strength = min((ema_l_val - ema_s_val) / ema_l_val * 100, 1.0)
                return {"signal": "SELL", "strength": strength}
            else:
                return {"signal": "HOLD", "strength": 0}
        
        signal_node = Node(
            input=[ema_short, ema_long, rsi_node],
            compute_fn=generate_signal,
            name="combined_signal",
        )
        
        self.add_nodes([
            price_stream,
            ema_short,
            ema_long,
            rsi_node,
            signal_node,
        ])


def create_strategy() -> Strategy:
    """Create and return the strategy instance."""
    return MultiIndicatorStrategy()

"""Binance integration via CCXT.

This module provides Binance brokerage integration.
"""

from __future__ import annotations

try:
    import ccxt  # type: ignore[import-untyped]
except ImportError:
    ccxt = None


class BinanceBroker:
    """Binance broker interface."""

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True):
        """Initialize Binance broker.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet if True
        """
        if ccxt is None:
            raise ImportError("CCXT is required for Binance integration. Install with: pip install ccxt")
        
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {'defaultType': 'future' if testnet else 'spot'},
        })
        
        if testnet:
            self.exchange.set_sandbox_mode(True)

    def place_order(self, symbol: str, side: str, amount: float, order_type: str = "market"):
        """Place an order.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT")
            side: Order side ("buy" or "sell")
            amount: Order amount
            order_type: Order type ("market" or "limit")

        Returns:
            Order result
        """
        return self.exchange.create_order(
            symbol=symbol,
            type=order_type,
            side=side,
            amount=amount,
        )

    def get_balance(self):
        """Get account balance."""
        return self.exchange.fetch_balance()


def create_broker(testnet: bool = True):
    """Create Binance broker instance.

    Args:
        testnet: Use testnet if True

    Returns:
        Configured BinanceBroker
    """
    # Load API credentials from environment or config
    import os
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    return BinanceBroker(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )

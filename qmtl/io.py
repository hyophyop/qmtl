"""IO module alias for qmtl.runtime.io"""

# Make binance_fetcher available
import sys

# Import the binance_fetcher module
import qmtl.runtime.io.binance_fetcher as binance_fetcher
from qmtl.runtime.io import *  # noqa: F403,F401

sys.modules[__name__ + '.binance_fetcher'] = binance_fetcher

__all__ = []  # Will be populated by the import above
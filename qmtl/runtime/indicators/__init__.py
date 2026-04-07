"""Technical indicator nodes built on top of ``qmtl.runtime.sdk``."""

from .anchored_vwap import anchored_vwap
from .atr import atr
from .bollinger_bands import bollinger_bands
from .chandelier_exit import chandelier_exit
from .ema import ema
from .ichimoku_cloud import ichimoku_cloud
from .kalman_trend import kalman_trend
from .kdj import kdj
from .keltner_channel import keltner_channel
from .microprice_priority import conditional_entry_filter, microprice_imbalance
from .obi_regime import obi_regime_node
from .obv import obv
from .order_book_obi import (
    order_book_depth_slope,
    order_book_imbalance_levels,
    order_book_obi,
    order_book_obi_ema,
    order_book_obiL_and_slope,
    priority_index,
)
from .rough_bergomi import rough_bergomi
from .rsi import rsi
from .sma import sma
from .stoch_rsi import stoch_rsi
from .supertrend import supertrend
from .twap import twap
from .volatility import volatility, volatility_node
from .vwap import vwap

# Optional alpha indicator; may not be available in all deployments
try:  # pragma: no cover - fallback for missing alpha module
    from .gap_amplification_alpha import gap_amplification_node
except Exception:  # pragma: no cover
    gap_amplification_node = None
from .helpers import alpha_indicator_with_history

__all__ = [
    "sma",
    "ema",
    "atr",
    "chandelier_exit",
    "ichimoku_cloud",
    "supertrend",
    "rsi",
    "kdj",
    "bollinger_bands",
    "keltner_channel",
    "obv",
    "vwap",
    "twap",
    "anchored_vwap",
    "kalman_trend",
    "rough_bergomi",
    "stoch_rsi",
    "volatility_node",
    "volatility",
    "order_book_obi",
    "order_book_obi_ema",
    "order_book_imbalance_levels",
    "order_book_depth_slope",
    "order_book_obiL_and_slope",
    "priority_index",
    "obi_regime_node",
    "microprice_imbalance",
    "conditional_entry_filter",
    "alpha_indicator_with_history",
]

if gap_amplification_node is not None:  # pragma: no cover
    __all__.append("gap_amplification_node")

"""Technical indicator nodes built on top of ``qmtl.runtime.sdk``."""

from .sma import sma
from .ema import ema
from .atr import atr
from .chandelier_exit import chandelier_exit
from .ichimoku_cloud import ichimoku_cloud
from .supertrend import supertrend
from .rsi import rsi
from .kdj import kdj
from .bollinger_bands import bollinger_bands
from .keltner_channel import keltner_channel
from .obv import obv
from .vwap import vwap
from .anchored_vwap import anchored_vwap
from .twap import twap
from .kalman_trend import kalman_trend
from .rough_bergomi import rough_bergomi
from .stoch_rsi import stoch_rsi
from .volatility import volatility_node, volatility
from .order_book_obi import (
    order_book_obi,
    order_book_obi_ema,
    order_book_imbalance_levels,
    order_book_depth_slope,
    order_book_obiL_and_slope,
    priority_index,
)
from .obi_regime import obi_regime_node
from .microprice_priority import microprice_imbalance, conditional_entry_filter
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

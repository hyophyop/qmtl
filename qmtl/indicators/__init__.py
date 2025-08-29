"""Technical indicator nodes built on top of ``qmtl.sdk``."""

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
from .kalman_trend import kalman_trend
from .rough_bergomi import rough_bergomi
from .stoch_rsi import stoch_rsi
from .volatility import volatility_node, volatility
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
    "anchored_vwap",
    "kalman_trend",
    "rough_bergomi",
    "stoch_rsi",
    "volatility_node",
    "volatility",
    "alpha_indicator_with_history",
]

if gap_amplification_node is not None:  # pragma: no cover
    __all__.append("gap_amplification_node")

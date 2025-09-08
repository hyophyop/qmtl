"""CCXT-driven BrokerageModel factory.

Build a reasonable default :class:`BrokerageModel` for a crypto exchange by
auto-detecting maker/taker fees via ``ccxt`` when available, with safe fallbacks
otherwise. Designed for quick experiments where users can switch exchanges by
ID and get a consistent fee/slippage baseline.

Notes
-----
- ``ccxt`` is an optional dependency; import is lazy and guarded.
- Fee detection order:
  1) ``exchange.load_markets()`` and symbol-specific ``market['maker'|'taker']``
     (or any representative market if ``symbol`` not provided)
  2) ``exchange.fees['trading']['maker'|'taker']``
  3) Provided defaults (maker, taker)

- Fallback defaults use spot-like maker/taker unless explicitly overridden.
"""

from __future__ import annotations

from typing import Any, Tuple
import logging

from .brokerage_model import BrokerageModel
from .buying_power import CashBuyingPowerModel
from .fees import MakerTakerFeeModel
from .fill_models import ImmediateFillModel
from .slippage import NullSlippageModel, SpreadBasedSlippageModel


_log = logging.getLogger(__name__)

# Cache detected fees to avoid repeated network calls to load_markets
_FEE_CACHE: dict[tuple[str, str, bool, str | None], tuple[float, float]] = {}


def _default_fees(product: str, defaults: tuple[float, float] | None) -> tuple[float, float]:
    if defaults is not None:
        return float(defaults[0]), float(defaults[1])
    # Spot-like conservative defaults; futures can override via ``defaults=...``
    return 0.0002, 0.0007  # maker, taker


def _instantiate_ccxt_exchange(exchange_id: str, *, product: str, sandbox: bool) -> Any:
    try:  # pragma: no cover - optional dependency import path
        import ccxt  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("ccxt is required for fee detection; set detect_fees=False to skip") from exc

    # Some exchanges share the same id for spot/futures; ``defaultType`` guides market metadata
    options = {"defaultType": "future" if product == "futures" else "spot"}
    klass = getattr(ccxt, exchange_id)
    ex = klass({"enableRateLimit": True, "options": options})
    # Best-effort sandbox toggle
    try:
        if sandbox and hasattr(ex, "set_sandbox_mode"):
            ex.set_sandbox_mode(True)  # type: ignore[attr-defined]
    except Exception:
        try:
            if sandbox and hasattr(ex, "setSandboxMode"):
                getattr(ex, "setSandboxMode")(True)
        except Exception:
            pass
    return ex


def _try_detect_fees(
    exchange_id: str,
    *,
    product: str,
    symbol: str | None,
    sandbox: bool,
) -> tuple[float, float] | None:
    """Return (maker, taker) if detection succeeds; otherwise ``None``."""
    try:
        ex = _instantiate_ccxt_exchange(exchange_id, product=product, sandbox=sandbox)
    except Exception as exc:  # pragma: no cover - exercised by separate fallback test
        _log.warning("CCXT import/instantiate failed for %s: %s", exchange_id, exc)
        return None

    maker: float | None = None
    taker: float | None = None

    # 1) Prefer market['maker'|'taker'] from load_markets
    try:
        markets = ex.load_markets()
        if symbol and symbol in markets:
            m = markets[symbol]
            maker = float(m.get("maker")) if m.get("maker") is not None else None
            taker = float(m.get("taker")) if m.get("taker") is not None else None
        if maker is None or taker is None:
            # try any representative market
            for m in markets.values():
                mk = m.get("maker")
                tk = m.get("taker")
                if mk is not None and tk is not None:
                    maker = float(mk)
                    taker = float(tk)
                    break
    except Exception:
        pass

    # 2) Exchange-level trading fees
    if maker is None or taker is None:
        try:
            fees = getattr(ex, "fees", {}) or {}
            trading = fees.get("trading", {}) if isinstance(fees, dict) else {}
            mk = trading.get("maker")
            tk = trading.get("taker")
            if mk is not None and tk is not None:
                maker = float(mk)
                taker = float(tk)
        except Exception:
            pass

    if maker is None or taker is None:
        return None
    return maker, taker


def make_ccxt_brokerage(
    exchange_id: str,
    *,
    product: str = "spot",
    symbol: str | None = None,
    sandbox: bool = False,
    detect_fees: bool = True,
    defaults: tuple[float, float] | None = None,
    use_spread_slippage: bool = False,
    spread_fraction: float = 0.5,
) -> BrokerageModel:
    """Build a :class:`BrokerageModel` using CCXT to detect maker/taker fees.

    Parameters
    ----------
    exchange_id:
        CCXT exchange id, e.g., ``"binance"`` or ``"binanceusdm"``.
    product:
        ``"spot"`` (default) or ``"futures"``. Guides CCXT market metadata and docs.
    symbol:
        Optional symbol like ``"BTC/USDT"`` used for symbol-specific fee selection.
    sandbox:
        When True, toggles exchange testnet mode if supported.
    detect_fees:
        If False, skip CCXT entirely and use ``defaults``.
    defaults:
        Fallback (maker, taker) used when detection fails or is disabled. If
        omitted, conservative spot-like defaults are used.
    use_spread_slippage:
        When True, use :class:`SpreadBasedSlippageModel` with ``spread_fraction``.
        Otherwise, :class:`NullSlippageModel` is used.
    spread_fraction:
        Fraction of the quoted spread to apply as slippage if ``use_spread_slippage``.
    """

    cache_key = (exchange_id, product, bool(sandbox), symbol)

    maker: float
    taker: float

    if detect_fees:
        cached = _FEE_CACHE.get(cache_key)
        if cached is not None:
            maker, taker = cached
        else:
            detected = _try_detect_fees(exchange_id, product=product, symbol=symbol, sandbox=sandbox)
            if detected is not None:
                maker, taker = detected
                _FEE_CACHE[cache_key] = (maker, taker)
            else:
                maker, taker = _default_fees(product, defaults)
                _log.warning(
                    "Using fallback maker/taker fees for %s (%s): maker=%s taker=%s",
                    exchange_id,
                    product,
                    maker,
                    taker,
                )
    else:
        maker, taker = _default_fees(product, defaults)

    fee_model = MakerTakerFeeModel(maker_rate=maker, taker_rate=taker)
    slippage_model = (
        SpreadBasedSlippageModel(spread_fraction=spread_fraction)
        if use_spread_slippage
        else NullSlippageModel()
    )
    model = BrokerageModel(
        buying_power_model=CashBuyingPowerModel(),
        fee_model=fee_model,
        slippage_model=slippage_model,
        fill_model=ImmediateFillModel(),
        symbols=None,  # crypto symbols typically validated by exchange; optional to plug custom provider
        hours=None,  # crypto 24/7 by default; plug ExchangeHoursProvider if desired
        shortable=None,
        settlement=None,
    )
    return model


__all__ = ["make_ccxt_brokerage"]


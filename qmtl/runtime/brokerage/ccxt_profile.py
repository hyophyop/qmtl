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

from typing import Any, Mapping
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


def _coerce_fee(value: Any) -> float | None:
    """Best-effort conversion to ``float`` while tolerating bad metadata."""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_maker_taker(candidate: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Return maker/taker floats (or ``None``) from CCXT metadata mapping."""

    maker = _coerce_fee(candidate.get("maker"))
    taker = _coerce_fee(candidate.get("taker"))
    return maker, taker


def _merge_fee_pair(
    base: tuple[float | None, float | None],
    candidate: tuple[float | None, float | None],
) -> tuple[float | None, float | None]:
    """Fill ``None`` entries in ``base`` using ``candidate`` values."""

    base_maker, base_taker = base
    cand_maker, cand_taker = candidate
    maker = base_maker if base_maker is not None else cand_maker
    taker = base_taker if base_taker is not None else cand_taker
    return maker, taker


def _detect_fees_from_markets(exchange: Any, symbol: str | None) -> tuple[float | None, float | None]:
    """Inspect ``load_markets`` metadata for maker/taker fees."""

    markets = exchange.load_markets()
    maker: float | None = None
    taker: float | None = None

    if symbol and symbol in markets:
        maker, taker = _extract_maker_taker(markets[symbol])
        if maker is not None and taker is not None:
            return maker, taker

    for market in markets.values():
        maker, taker = _merge_fee_pair((maker, taker), _extract_maker_taker(market))
        if maker is not None and taker is not None:
            break

    return maker, taker


def _detect_fees_from_trading(exchange: Any, _: str | None) -> tuple[float | None, float | None]:
    """Inspect exchange-level trading fees for maker/taker values."""

    fees = getattr(exchange, "fees", {}) or {}
    if not isinstance(fees, Mapping):
        return None, None

    trading = fees.get("trading", {})
    if not isinstance(trading, Mapping):
        return None, None

    return _extract_maker_taker(trading)


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

    detectors = (
        _detect_fees_from_markets,
        _detect_fees_from_trading,
    )

    for detector in detectors:
        if maker is not None and taker is not None:
            break
        try:
            detected = detector(ex, symbol)
        except Exception:
            continue
        maker, taker = _merge_fee_pair((maker, taker), detected)

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


def make_ccxt_spot_brokerage(
    exchange_id: str,
    *,
    symbol: str | None = None,
    sandbox: bool = False,
    detect_fees: bool = True,
    defaults: tuple[float, float] | None = None,
) -> BrokerageModel:
    """Convenience wrapper for spot exchanges with spread-based slippage."""

    return make_ccxt_brokerage(
        exchange_id,
        product="spot",
        symbol=symbol,
        sandbox=sandbox,
        detect_fees=detect_fees,
        defaults=defaults,
        use_spread_slippage=True,
    )


__all__ = ["make_ccxt_brokerage", "make_ccxt_spot_brokerage"]


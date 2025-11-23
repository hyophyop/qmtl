from __future__ import annotations

"""Standard brokerage client interfaces and reference implementations.

This module defines a minimal, reusable surface for submitting and
monitoring live orders across different brokers. It intentionally keeps
the order shape generic (a dict) to avoid overfitting to any single
provider. The Runner can continue to use TradeExecutionService directly;
HttpBrokerageClient simply wraps it for a stable interface. A lightweight
FakeBrokerageClient is provided for demos/tests, and a CCXT-based client
is included as a reference connector when ``ccxt`` is available.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, TypedDict

from .trade_execution_service import TradeExecutionService


def _call_exchange_method(target: Any, method_names: tuple[str, ...], *args: Any) -> bool:
    for name in method_names:
        method = getattr(target, name, None)
        if not callable(method):
            continue
        try:
            method(*args)
            return True
        except Exception:
            continue
    return False


def _enable_sandbox_mode(exchange: CcxtExchange, sandbox: bool) -> None:
    if not sandbox:
        return
    _call_exchange_method(exchange, ("set_sandbox_mode", "setSandboxMode"), True)


def _build_ccxt_config(kwargs: dict[str, Any]) -> tuple[CcxtClientConfig, bool]:
    sandbox = bool(kwargs.pop("sandbox", kwargs.pop("testnet", False)))
    enable_rate_limit = kwargs.pop("enableRateLimit", True)
    config: CcxtClientConfig = {
        "apiKey": kwargs.pop("apiKey", None) or kwargs.pop("api_key", None),
        "secret": kwargs.pop("secret", None),
        "enableRateLimit": enable_rate_limit,
    }
    options = kwargs.pop("options", None)
    if options is not None:
        config["options"] = options
    return config, sandbox


class BrokerageClient(ABC):
    """Abstract brokerage client.

    Implementations should be resilient to transient errors and provide a
    best-effort ``poll_order_status`` to report completion.
    """

    @abstractmethod
    def post_order(self, order: dict[str, Any]) -> Any:  # pragma: no cover - interface
        """Submit an order payload to the broker and return a response object."""

    @abstractmethod
    def poll_order_status(self, order: dict[str, Any]) -> Any | None:  # pragma: no cover - interface
        """Poll broker for order completion, returning a response or ``None`` if pending/unknown."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> Any | None:  # pragma: no cover - interface
        """Attempt to cancel the order. Return provider response or ``None`` if unsupported."""


class HttpBrokerageClient(BrokerageClient):
    """HTTP brokerage client wrapping ``TradeExecutionService``.

    Parameters
    ----------
    url:
        Base broker endpoint. ``post_order`` sends to this URL; ``poll_order_status``
        and ``cancel_order`` call ``{url}/{id}`` for GET/DELETE respectively.
    max_retries:
        Number of POST retries for transient failures (default 3).
    backoff:
        Base backoff seconds between retries (default 0.1s).
    """

    def __init__(self, url: str, *, max_retries: int = 3, backoff: float = 0.1) -> None:
        self._svc = TradeExecutionService(url, max_retries=max_retries, backoff=backoff)
        self._url = url

    def post_order(self, order: dict[str, Any]) -> Any:
        return self._svc.post_order(order)

    def poll_order_status(self, order: dict[str, Any]) -> Any | None:
        return self._svc.poll_order_status(order)

    def cancel_order(self, order_id: str) -> Any | None:
        # Best-effort: DELETE {url}/{id}. Not all brokers support this REST shape.
        try:
            import httpx

            resp = httpx.delete(f"{self._url}/{order_id}", timeout=10.0)
            resp.raise_for_status()
            return resp
        except Exception:
            return None


class FakeBrokerageClient(BrokerageClient):
    """In-memory fake broker for demos/tests.

    - Assigns incremental IDs and immediately marks orders as completed.
    - Returns dict responses with fields: ``id``, ``status``, ``echo``.
    """

    def __init__(self) -> None:
        self._last_id = 0
        self._store: dict[str, dict[str, Any]] = {}

    def _next_id(self) -> str:
        self._last_id += 1
        return str(self._last_id)

    def post_order(self, order: dict[str, Any]) -> Any:
        oid = self._next_id()
        rec = {"id": oid, "status": "completed", "echo": order}
        self._store[oid] = rec
        return rec

    def poll_order_status(self, order: dict[str, Any]) -> Any | None:
        oid = str(order.get("id") or "")
        if oid and oid in self._store:
            return self._store[oid]
        # If the order didn't have an id, treat it as immediately done (fake broker).
        return {"status": "completed", "echo": order}

    def cancel_order(self, order_id: str) -> Any | None:
        if order_id in self._store:
            self._store[order_id]["status"] = "canceled"
            return self._store[order_id]
        return None


class CcxtBrokerageClient(BrokerageClient):
    """Minimal CCXT-based connector (reference implementation).

    Notes
    -----
    - Requires ``ccxt`` to be installed. Import is lazy and a helpful error is raised otherwise.
    - Expects order payload fields: ``symbol``, ``side`` (BUY/SELL), ``type`` (market/limit),
      ``quantity`` (amount), optional ``limit_price`` and ``time_in_force``.
    - API credentials are read from the provided kwargs or ``CCXT_API_KEY``/``CCXT_SECRET`` env vars.
    - This is a thin demo; production deployments should manage auth, nonce, rate-limits,
      and exchange-specific nuances carefully.
    - Constructor kwargs follow :class:`CcxtClientConfig` for the documented parameters; any
      additional keys are forwarded directly to the CCXT exchange constructor.
    """

    def __init__(self, exchange: str, **kwargs: Any) -> None:
        try:
            import ccxt
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("ccxt is required for CcxtBrokerageClient") from exc

        config, sandbox = _build_ccxt_config(kwargs)
        ccxt_kwargs: dict[str, Any] = {**kwargs, **config}

        klass = getattr(ccxt, exchange)
        self._ex: CcxtExchange = klass(ccxt_kwargs)
        _enable_sandbox_mode(self._ex, sandbox)

    def post_order(self, order: dict[str, Any]) -> Any:
        symbol = order.get("symbol")
        side = (order.get("side") or "").lower()
        typ = (order.get("type") or "market").lower()
        amount = order.get("quantity") or order.get("amount")
        price = order.get("limit_price") or order.get("price")
        params: dict[str, Any] = {}
        tif = order.get("time_in_force") or order.get("tif")
        if tif:
            params["timeInForce"] = str(tif).upper()
        if symbol is None or side not in {"buy", "sell"} or amount is None:
            raise ValueError("symbol, side in {buy,sell}, and quantity are required")
        return self._ex.create_order(symbol, typ, side, amount, price, params)

    def poll_order_status(self, order: dict[str, Any]) -> Any | None:
        oid = order.get("id")
        symbol = order.get("symbol")
        if not oid or not symbol:
            return None
        try:
            return self._ex.fetch_order(oid, symbol)
        except Exception:
            return None

    def cancel_order(self, order_id: str) -> Any | None:
        try:
            return self._ex.cancel_order(order_id)
        except Exception:
            return None


class FuturesCcxtBrokerageClient(BrokerageClient):
    """CCXT futures (perpetual) connector with Binance USDT-M defaults.

    Parameters
    ----------
    exchange:
        CCXT exchange id (default: "binanceusdm").
    symbol:
        Optional symbol used to apply leverage/margin defaults at init.
    leverage:
        Optional leverage to set (e.g., 5). Some exchanges require per-symbol.
    margin_mode:
        "cross" (default) or "isolated". Applied best-effort if supported.
    hedge_mode:
        If True, attempt to enable dual-side (hedge) position mode.
    sandbox/testnet:
        When True, route to exchange testnet endpoints if supported.
    options/kwargs:
        Forwarded to the CCXT exchange constructor.
    """

    def __init__(
        self,
        exchange: str = "binanceusdm",
        *,
        symbol: str | None = None,
        leverage: int | None = None,
        margin_mode: str = "cross",
        hedge_mode: bool | None = None,
        **kwargs: Any,
    ) -> None:
        ccxt_module = self._import_ccxt_module()

        options = kwargs.pop("options", {}) or {}
        options.setdefault("defaultType", "future")
        kwargs["options"] = options
        config, sandbox = _build_ccxt_config(kwargs)

        klass = getattr(ccxt_module, exchange)
        self._ex: CcxtExchange = klass({**kwargs, **config})
        self._default_margin_mode = margin_mode
        self._default_leverage = leverage
        self._symbol_prefs_applied: set[str] = set()

        _enable_sandbox_mode(self._ex, sandbox)

        self._apply_position_mode(hedge_mode)
        self._apply_symbol_defaults(symbol, margin_mode=margin_mode, leverage=leverage)

    def post_order(self, order: dict[str, Any]) -> Any:
        symbol = order.get("symbol")
        side = (order.get("side") or "").lower()
        typ = (order.get("type") or "market").lower()
        amount = order.get("quantity") or order.get("amount")
        price = order.get("limit_price") or order.get("price")
        params = self._build_order_params(order)

        self._apply_order_leverage(order, symbol)
        if symbol:
            self._apply_symbol_defaults(
                symbol,
                margin_mode=self._default_margin_mode,
                leverage=self._default_leverage,
            )

        if symbol is None or side not in {"buy", "sell"} or amount is None:
            raise ValueError("symbol, side in {buy,sell}, and quantity are required")
        return self._ex.create_order(symbol, typ, side, amount, price, params)

    def poll_order_status(self, order: dict[str, Any]) -> Any | None:
        oid = order.get("id")
        symbol = order.get("symbol")
        if not oid or not symbol:
            return None
        try:
            return self._ex.fetch_order(oid, symbol)
        except Exception:
            return None

    def cancel_order(self, order_id: str) -> Any | None:
        try:
            return self._ex.cancel_order(order_id)
        except Exception:
            return None

    @staticmethod
    def _import_ccxt_module() -> CcxtModule:
        try:
            import ccxt
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("ccxt is required for FuturesCcxtBrokerageClient") from exc
        return ccxt

    @staticmethod
    def _normalize_margin_mode(mode: str | None) -> str | None:
        if not mode:
            return None
        return "ISOLATED" if str(mode).lower() == "isolated" else "CROSS"

    def _apply_position_mode(self, hedge_mode: bool | None) -> None:
        if hedge_mode is None:
            return
        _call_exchange_method(self._ex, ("set_position_mode",), bool(hedge_mode))

    def _apply_symbol_defaults(
        self,
        symbol: str | None,
        *,
        margin_mode: str | None,
        leverage: int | None,
    ) -> None:
        if not symbol or symbol in self._symbol_prefs_applied:
            return

        normalized_mode = self._normalize_margin_mode(margin_mode)
        attempted = False
        all_succeeded = True

        if normalized_mode:
            attempted = True
            if not _call_exchange_method(
                self._ex,
                ("set_margin_mode",),
                normalized_mode,
                symbol,
            ):
                all_succeeded = False

        if leverage is not None:
            attempted = True
            if not _call_exchange_method(
                self._ex,
                ("set_leverage",),
                int(leverage),
                symbol,
            ):
                all_succeeded = False

        if not attempted or all_succeeded:
            self._symbol_prefs_applied.add(symbol)

    def _apply_order_leverage(self, order: dict[str, Any], symbol: str | None) -> None:
        if not symbol:
            return
        lev = order.get("leverage")
        if lev is None:
            return
        _call_exchange_method(self._ex, ("set_leverage",), int(lev), symbol)

    @staticmethod
    def _build_order_params(order: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        tif = order.get("time_in_force") or order.get("tif")
        if tif:
            params["timeInForce"] = str(tif).upper()
        reduce_only = order.get("reduce_only") or order.get("reduceOnly")
        if reduce_only is not None:
            params["reduceOnly"] = bool(reduce_only)
        pos_side = order.get("position_side") or order.get("positionSide")
        if pos_side:
            params["positionSide"] = str(pos_side).upper()
        cid = order.get("client_order_id") or order.get("newClientOrderId")
        if cid:
            params["newClientOrderId"] = str(cid)
        return params


__all__ = [
    "BrokerageClient",
    "HttpBrokerageClient",
    "FakeBrokerageClient",
    "CcxtBrokerageClient",
    "FuturesCcxtBrokerageClient",
]
class CcxtExchange(Protocol):
    def create_order(
        self,
        symbol: str,
        typ: str,
        side: str,
        amount: Any,
        price: Any,
        params: dict[str, Any] | None = None,
    ) -> Any:  # pragma: no cover - protocol signature
        ...

    def fetch_order(self, order_id: Any, symbol: str | None = None) -> Any:  # pragma: no cover - protocol signature
        ...

    def cancel_order(self, order_id: str, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - protocol signature
        ...

    def set_sandbox_mode(self, enabled: bool) -> Any:  # pragma: no cover - protocol signature
        ...

    def setSandboxMode(self, enabled: bool) -> Any:  # pragma: no cover - protocol signature
        ...

    def set_position_mode(self, hedge_mode: bool) -> Any:  # pragma: no cover - protocol signature
        ...

    def set_margin_mode(self, mode: str, symbol: str) -> Any:  # pragma: no cover - protocol signature
        ...

    def set_leverage(self, leverage: int, symbol: str) -> Any:  # pragma: no cover - protocol signature
        ...


class CcxtClientConfig(TypedDict, total=False):
    apiKey: str | None
    secret: str | None
    enableRateLimit: bool
    options: dict[str, Any]


class CcxtModule(Protocol):
    def __getattr__(self, name: str) -> type[CcxtExchange]:  # pragma: no cover - protocol signature
        ...

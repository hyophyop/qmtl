from __future__ import annotations

from typing import Any

from qmtl.runtime.io import CcxtQuestDBProvider


class _StubOHLCVExchange:
    async def fetch_ohlcv(self, symbol: str, timeframe: str, **kwargs: Any):
        return [[60_000, 1, 1, 1, 1, 1]]

    async def close(self):  # pragma: no cover
        pass


class _StubTradesExchange:
    async def fetch_trades(self, symbol: str, **kwargs: Any):
        return [{"timestamp": 60_000, "price": 1.0, "amount": 0.1, "side": "buy"}]

    async def close(self):  # pragma: no cover
        pass


def _base_cfg(**extra: object) -> dict[str, object]:
    return {
        "exchange": "binance",
        "symbols": ["BTC/USDT"],
        "questdb": {
            "dsn": "postgresql://localhost:8812/qdb",
            "table": "crypto",
        },
        **extra,
    }


def test_from_config_multi_trades_builds_expected_nodes():
    cfg = _base_cfg(mode="trades", symbols=["BTC/USDT", "ETH/USDT"], timeframes=["1m"])
    providers = CcxtQuestDBProvider.from_config_multi(cfg, exchange=_StubTradesExchange())

    expected = {
        "trades:binance:BTC/USDT",
        "trades:binance:ETH/USDT",
    }
    assert set(providers) == expected
    assert all(isinstance(p, CcxtQuestDBProvider) for p in providers.values())


def test_from_config_multi_ohlcv_respects_timeframes():
    cfg = _base_cfg(symbols=["BTC/USDT"], timeframes=["1m", "5m"])
    providers = CcxtQuestDBProvider.from_config_multi(cfg, exchange=_StubOHLCVExchange())

    expected = {
        "ohlcv:binance:BTC/USDT:1m",
        "ohlcv:binance:BTC/USDT:5m",
    }
    assert set(providers) == expected


def test_from_config_multi_returns_empty_without_symbols():
    cfg = _base_cfg(symbols=[])
    assert CcxtQuestDBProvider.from_config_multi(cfg) == {}

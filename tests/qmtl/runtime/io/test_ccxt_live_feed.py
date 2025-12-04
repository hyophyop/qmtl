import asyncio

import pytest

from qmtl.runtime.io import ccxt_live_feed as live_module
from qmtl.runtime.io.ccxt_live_feed import CcxtProConfig, CcxtProLiveFeed


class _FlakyOHLCVExchange:
    def __init__(self) -> None:
        self.calls = 0

    async def watch_ohlcv(self, symbol: str, timeframe: str):
        self.calls += 1
        if self.calls <= 3:
            raise RuntimeError("boom")
        base_ms = 1_700_000_000_000
        return [[base_ms + (self.calls * 60_000), 100.0, 110.0, 90.0, 105.0, 12.0]]


class _DuplicateOHLCVExchange:
    def __init__(self) -> None:
        self.calls = 0

    async def watch_ohlcv(self, symbol: str, timeframe: str):
        self.calls += 1
        base_ms = 1_700_000_000_000
        if self.calls == 1:
            return [
                [base_ms, 100.0, 110.0, 90.0, 105.0, 12.0],
                [base_ms, 100.0, 110.0, 90.0, 105.0, 12.0],
                [base_ms + 60_000, 101.0, 111.0, 91.0, 106.0, 13.0],
            ]
        if self.calls == 2:
            return [
                [base_ms + 60_000, 101.0, 111.0, 91.0, 106.0, 13.0],
                [base_ms + 120_000, 102.0, 112.0, 92.0, 107.0, 14.0],
            ]
        return []


class _TradesExchange:
    def __init__(self) -> None:
        self.calls = 0

    async def watch_trades(self, symbol: str):
        self.calls += 1
        base_ms = 1_700_000_000_000
        if self.calls == 1:
            return [
                {"timestamp": base_ms, "price": 100.0, "amount": 1.0, "side": "buy"},
                {"timestamp": base_ms, "price": 100.5, "amount": 1.2, "side": "buy"},
            ]
        if self.calls == 2:
            return [
                {"timestamp": base_ms, "price": 100.25, "amount": 0.8, "side": "buy"},
                {"timestamp": base_ms + 1000, "price": 101.0, "amount": 2.0, "side": "sell"},
            ]
        return []


@pytest.mark.asyncio
async def test_reconnect_backoff_schedule(monkeypatch):
    sleep_calls: list[float] = []

    original_sleep = live_module.asyncio.sleep

    async def _fake_sleep(delay: float):
        sleep_calls.append(delay)
        await original_sleep(0)

    monkeypatch.setattr(live_module.asyncio, "sleep", _fake_sleep)

    config = CcxtProConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        reconnect_backoff_ms=[100, 250],
        emit_building_candle=True,
    )
    feed = CcxtProLiveFeed(config, exchange=_FlakyOHLCVExchange())

    gen = feed.subscribe(node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    ts, frame = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
    assert not frame.empty
    assert ts == int(frame["ts"].iloc[-1])

    feed.unsubscribe(node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=0.05)

    positive_calls = [call for call in sleep_calls if call and call > 0]
    assert positive_calls == [0.1, 0.25, 0.25]


@pytest.mark.asyncio
async def test_dedupe_by_symbol():
    config = CcxtProConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        mode="trades",
        dedupe_by="ts+symbol",
    )
    feed = CcxtProLiveFeed(config, exchange=_TradesExchange())

    gen = feed.subscribe(node_id="trades:binance:BTC/USDT", interval=0)
    first_ts, first_df = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
    assert list(first_df["ts"]) == [1_700_000_000]
    assert list(first_df["symbol"]) == ["BTC/USDT"]

    second_ts, second_df = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
    assert list(second_df["ts"]) == [1_700_000_001]
    assert list(second_df["symbol"]) == ["BTC/USDT"]
    assert second_ts == 1_700_000_001

    feed.unsubscribe(node_id="trades:binance:BTC/USDT", interval=0)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=0.05)

    stored_token = next(iter(feed._last_emitted_token.values()))
    assert stored_token == (1_700_000_001, "BTC/USDT")


@pytest.mark.asyncio
async def test_ohlcv_dedupe_helper():
    config = CcxtProConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        emit_building_candle=True,
    )
    feed = CcxtProLiveFeed(config, exchange=_DuplicateOHLCVExchange())

    gen = feed.subscribe(node_id="ohlcv:binance:BTC/USDT:1m", interval=60)

    first_ts, first_df = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
    assert list(first_df["ts"]) == [1_700_000_000, 1_700_000_060]
    assert first_ts == 1_700_000_060

    second_ts, second_df = await asyncio.wait_for(gen.__anext__(), timeout=0.1)
    assert list(second_df["ts"]) == [1_700_000_120]
    assert second_ts == 1_700_000_120

    feed.unsubscribe(node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=0.05)

    stored_token = next(iter(feed._last_emitted_token.values()))
    assert stored_token == 1_700_000_120

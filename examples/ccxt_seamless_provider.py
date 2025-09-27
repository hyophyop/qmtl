"""CCXT × Seamless Data Provider end-to-end example.

이 스크립트는 CCXT 백필 구성과 Seamless Data Provider를 결합해
단일 노드에서 자동 백필, 라이브 데이터, 커버리지 확인까지 수행하는
방법을 보여 줍니다.

실행 전 준비 사항:

1. 의존성 설치: ``uv pip install -e .[dev,ccxt,questdb]``
2. QuestDB 실행: ``docker run -p 8812:8812 -p 9000:9000 questdb/questdb:latest``
3. (선택) Redis 실행: ``docker run -p 6379:6379 redis:7-alpine``
4. 환경 변수로 CCXT API 키 설정 (공개 엔드포인트만 사용한다면 생략 가능)

예제는 Binance의 BTC/USDT 1분 봉을 대상으로 하며, 필요에 따라
심볼·타임프레임을 변경해 사용할 수 있습니다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pandas as pd

from qmtl.runtime.io import (
    CcxtBackfillConfig,
    CcxtOHLCVFetcher,
    CcxtProConfig,
    CcxtProLiveFeed,
)
from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy


@dataclass(slots=True)
class ExampleSettings:
    """High-level knobs for the demo."""

    exchange: str = "binance"
    symbols: list[str] = ("BTC/USDT",)
    timeframe: str = "1m"
    questdb_dsn: str = "postgresql://localhost:8812/qmtl"
    questdb_table: str = "ohlcv"
    interval_seconds: int = 60
    backfill_batch: int = 500
    earliest_ts: int = 1_577_836_800  # 2020-01-01 UTC
    start: int = 1_706_745_600  # 2024-01-01 00:00:00 UTC
    end: int = 1_706_832_000    # 2024-01-01 24:00:00 UTC
    enable_live_feed: bool = True


async def build_provider(settings: ExampleSettings) -> EnhancedQuestDBProvider:
    """Create a Seamless provider wired with CCXT fetchers and optional live feed."""

    backfill_config = CcxtBackfillConfig(
        exchange=settings.exchange,
        symbols=list(settings.symbols),
        timeframe=settings.timeframe,
        batch_limit=settings.backfill_batch,
        earliest_ts=settings.earliest_ts,
    )
    fetcher = CcxtOHLCVFetcher(backfill_config)

    live_feed = None
    if settings.enable_live_feed:
        live_feed = CcxtProLiveFeed(
            CcxtProConfig(
                exchange=settings.exchange,
                symbols=list(settings.symbols),
                timeframe=settings.timeframe,
            )
        )

    provider = EnhancedQuestDBProvider(
        dsn=settings.questdb_dsn,
        table=settings.questdb_table,
        fetcher=fetcher,
        live_feed=live_feed,
        strategy=DataAvailabilityStrategy.SEAMLESS,
    )

    return provider


async def fetch_history(provider: EnhancedQuestDBProvider, settings: ExampleSettings) -> pd.DataFrame:
    """Fetch the requested range and print a short summary."""

    node_id = f"ohlcv:{settings.exchange}:{settings.symbols[0]}:{settings.timeframe}"

    print("▶ Fetching historical window")
    frame = await provider.fetch(
        start=settings.start,
        end=settings.end,
        node_id=node_id,
        interval=settings.interval_seconds,
    )
    print(f"- rows: {len(frame)}")
    if not frame.empty:
        print(frame.head())

    print("▶ Coverage report")
    coverage = await provider.coverage(node_id=node_id, interval=settings.interval_seconds)
    for covered_start, covered_end in coverage:
        print(f"  - {covered_start} → {covered_end}")

    return frame


async def main() -> None:
    settings = ExampleSettings()
    provider = await build_provider(settings)

    # Optional: persist artifacts locally for reproducibility
    # os.environ["QMTL_SEAMLESS_ARTIFACTS"] = "1"

    await fetch_history(provider, settings)

    if settings.enable_live_feed:
        print("▶ Waiting briefly for live feed hydration (5 seconds)...")
        await asyncio.sleep(5)

        node_id = f"ohlcv:{settings.exchange}:{settings.symbols[0]}:{settings.timeframe}"
        latest = await provider.fetch(
            start=settings.end - settings.interval_seconds * 5,
            end=settings.end,
            node_id=node_id,
            interval=settings.interval_seconds,
        )
        if not latest.empty:
            print("- latest bars")
            print(latest.tail())
        else:
            print("- live feed returned no additional rows yet")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

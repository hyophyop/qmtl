---
title: "CCXT Seamless Data Provider 사용 가이드"
tags: [guide, ccxt, seamless]
author: "QMTL Team"
last_modified: 2025-08-21
---

# CCXT Seamless Data Provider 사용 가이드

CCXT 기반 거래소 데이터를 QMTL의 Seamless Data Provider와 결합하면 자동 백필·라이브 전환·커버리지 관리를 단일 인터페이스에서 처리할 수 있습니다. 이 문서는 `CcxtOHLCVFetcher`를 `EnhancedQuestDBProvider`에 연결해 실전 전략에 적용하는 절차를 정리합니다.

> 상세 아키텍처는 [CCXT × Seamless 통합 아키텍처](../architecture/ccxt-seamless-integrated.md)를 참고하세요.

## 사전 준비

| 구성 요소 | 목적 | 준비 방법 |
| --- | --- | --- |
| Python 환경 | QMTL 및 ccxt 의존성 설치 | `uv pip install -e .[dev,ccxt,questdb]` |
| QuestDB | 히스토리 저장소 | `docker run -p 8812:8812 -p 9000:9000 questdb/questdb:latest` |
| (선택) Redis | 클러스터 레이트리밋 공유 | `docker run -p 6379:6379 redis:7-alpine` 후 `connectors.ccxt_rate_limiter_redis: redis://localhost:6379/0` 설정 (`QMTL_CCXT_RATE_LIMITER_REDIS` 지원) |
| CCXT API 키 | 사설 엔드포인트/고빈도 요청 | 거래소 콘솔 발급 후 `CCXT_APIKEY`, `CCXT_SECRET` 환경 변수로 주입 |

## 핵심 구성 요소

1. **백필 설정** – `CcxtBackfillConfig`에 거래소, 심볼, 타임프레임, 페이징 정책을 정의합니다.
2. **데이터 페처** – `CcxtOHLCVFetcher`는 CCXT로 OHLCV 캔들을 비동기로 수집합니다.
3. **Seamless Provider** – `EnhancedQuestDBProvider`에 페처를 연결하면 자동 백필/캐시/라이브 피드가 하나의 인터페이스로 노출됩니다.
4. **라이브 피드(선택)** – `CcxtProLiveFeed` 또는 커스텀 `LiveDataFeed`로 실시간 갱신을 연결할 수 있습니다.

아래 예시는 1분 봉 데이터를 처리하는 최소 구성을 보여 줍니다. 전체 스크립트는 `examples/ccxt_seamless_provider.py`를 참고하세요.

```python
import asyncio

from qmtl.runtime.io import CcxtBackfillConfig, CcxtOHLCVFetcher
from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy

async def main() -> None:
    backfill = CcxtBackfillConfig(
        exchange="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        batch_limit=500,
        earliest_ts=1_577_836_800,
    )
    fetcher = CcxtOHLCVFetcher(backfill)

    provider = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        table="ohlcv",
        fetcher=fetcher,
        strategy=DataAvailabilityStrategy.SEAMLESS,
    )

    frame = await provider.fetch(
        start=1_706_745_600,
        end=1_706_832_000,
        node_id="ohlcv:binance:BTC/USDT:1m",
        interval=60,
    )
    print(frame.head())

if __name__ == "__main__":
    asyncio.run(main())
```

## 라이브 피드 통합

실시간 캔들이 필요하면 `CcxtProLiveFeed`를 Seamless provider에 연결합니다.

```python
from qmtl.runtime.io import CcxtProLiveFeed, CcxtProConfig

live_feed = CcxtProLiveFeed(
    CcxtProConfig(
        exchange="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
    )
)

provider = EnhancedQuestDBProvider(
    dsn="postgresql://localhost:8812/qmtl",
    table="ohlcv",
    fetcher=fetcher,
    live_feed=live_feed,
    strategy=DataAvailabilityStrategy.SEAMLESS,
)
```

Seamless 런타임은 아래 순서로 데이터를 처리합니다.

1. **캐시/스토리지** – 요청 구간이 QuestDB에 있으면 즉시 반환합니다.
2. **백필** – 공백 구간은 CCXT에서 자동 백필 후 QuestDB에 적재합니다.
3. **라이브 피드** – 최신 캔들이 아직 저장되지 않았다면 실시간 피드로 채웁니다.

## 전략/DAG 연동

`StreamInput` 등 `HistoryProvider` 인터페이스를 사용하는 노드에 Seamless provider를 그대로 주입하면 됩니다.

```python
from qmtl.runtime.sdk.nodes.sources import StreamInput

price = StreamInput(
    tags=["btc", "spot"],
    interval="60s",
    period=3600,
    history_provider=provider,
)
```

Seamless provider는 DAG가 요청한 범위를 충족할 때까지 백그라운드 백필과 SLA 측정을 자동으로 수행합니다. `qmtl.yml`의 `seamless.artifacts_enabled`를 활성화하면 로컬 개발 중 `~/.qmtl_seamless_artifacts/`에 Parquet 아티팩트가 저장되어 재현성을 높일 수 있습니다.

## 운영 체크리스트

- **커버리지 점검**: `provider.coverage(node_id=..., interval=...)`를 호출해 QuestDB 커버리지를 주기적으로 확인합니다.
- **모니터링**: `operations/monitoring/seamless_v2.jsonnet`을 배포해 `seamless_sla_deadline_seconds`, `seamless_conformance_flag_total` 등 대시보드를 활성화합니다.
- **레이트리밋**: 429가 발생하면 `batch_limit`을 줄이거나 `min_interval_ms`를 늘리고 Redis 토큰 버킷을 조정하세요.
- **에러 재현**: 여러 워커가 동일한 `seamless.coordinator_url`을 사용하면 백필 단일화를 위해 임계 구역을 공유합니다. 충돌 시 `seamless.backfill.coordinator_*` 로그를 확인하세요.

## 문제 해결 FAQ

| 증상 | 원인 | 대응 |
| --- | --- | --- |
| `RuntimeError: ccxt is required ...` | 선택 extras 미설치 | `uv pip install -e .[ccxt]` 실행 |
| QuestDB 연결 실패 | DSN 오타 또는 서버 미기동 | DSN 확인, QuestDB 컨테이너 상태 점검 |
| 백필 지연 | 레이트리밋 초과 | `batch_limit` 축소, `min_interval_ms` 증가, Redis 버킷 구성 |
| `seamless.sla.downgrade` 경고 | SLA 예산 초과 | `DataAvailabilityStrategy`를 `AUTO_BACKFILL`로 완화하거나 요청 구간을 축소 |

## 추가 자료

- `examples/ccxt_seamless_provider.py` – 전체 실행 예제
- [Seamless Migration to v2](seamless_migration_v2.md) – 레거시 히스토리 스택 전환 절차
- [CCXT × QuestDB (IO)](../io/ccxt-questdb.md) – QuestDB 백엔드 구성 및 레이트리밋 전략

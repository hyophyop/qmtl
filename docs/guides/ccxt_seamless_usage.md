# CCXT Seamless Data Provider 사용 가이드

CCXT 기반 거래소 데이터를 QMTL의 Seamless Data Provider와 결합하면, 단일 인터페이스로 자동 백필·라이브 전환·커버리지 관리를 처리할 수 있습니다. 이 문서는 `CcxtOHLCVFetcher`를 `EnhancedQuestDBProvider`에 연결해 실전 전략에서 바로 활용하는 방법을 단계별로 정리합니다.

> 더 깊은 설계 배경은 [CCXT × Seamless Integrated Architecture](../architecture/ccxt-seamless-integrated.md)에서 확인할 수 있습니다.

## 사전 준비

| 구성 요소 | 목적 | 준비 방법 |
| --- | --- | --- |
| Python 환경 | QMTL 및 ccxt 의존성 설치 | `uv pip install -e .[dev,ccxt,questdb]` |
| QuestDB | 히스토리 저장소 | `docker run -p 8812:8812 -p 9000:9000 questdb/questdb:latest` |
| (선택) Redis | 클러스터 레이트리밋 공유 | `docker run -p 6379:6379 redis:7-alpine` 후 `connectors.ccxt_rate_limiter_redis: redis://localhost:6379/0` (`QMTL_CCXT_RATE_LIMITER_REDIS` 레거시 지원) |
| CCXT API 키 | 사설 엔드포인트/고빈도 요청 시 필요 | 거래소 콘솔에서 발급 후 `CCXT_APIKEY`, `CCXT_SECRET` 환경변수로 주입 |

## 핵심 구성 요소

1. **백필 설정** – `CcxtBackfillConfig`로 거래소, 심볼, 타임프레임, 페이징 정책을 정의합니다.
2. **데이터 페처** – `CcxtOHLCVFetcher`는 CCXT를 통해 시세 캔들(OHLCV)을 비동기로 수집합니다.
3. **Seamless Provider** – `EnhancedQuestDBProvider`에 페처를 연결하면 자동 백필/캐시/라이브 피드가 하나의 전략 인터페이스로 노출됩니다.
4. **라이브 피드(선택)** – `CcxtProLiveFeed` 또는 커스텀 `LiveDataFeed`를 연결해 실시간 갱신을 받을 수 있습니다.

아래 예시는 최소 구성으로 1분 봉 데이터를 처리하는 방법을 보여 줍니다. 전체 스크립트는 `examples/ccxt_seamless_provider.py`에서 확인할 수 있습니다.

```python
import asyncio

from qmtl.runtime.io import CcxtBackfillConfig, CcxtOHLCVFetcher
from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy

async def main() -> None:
    backfill = CcxtBackfillConfig(
        exchange="binance",           # CCXT 교환소 ID
        symbols=["BTC/USDT"],         # 하나 이상의 심볼
        timeframe="1m",               # CCXT 규약 타임프레임
        batch_limit=500,               # API 당 최대 캔들 수
        earliest_ts=1_577_836_800,     # 필요 시 백필 하한 (예: 2020-01-01 UTC)
    )
    fetcher = CcxtOHLCVFetcher(backfill)

    provider = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        table="ohlcv",
        fetcher=fetcher,
        strategy=DataAvailabilityStrategy.SEAMLESS,
    )

    frame = await provider.fetch(
        start=1_706_745_600,  # 2024-01-01 00:00:00 UTC
        end=1_706_832_000,    # 2024-01-01 24:00:00 UTC
        node_id="ohlcv:binance:BTC/USDT:1m",
        interval=60,
    )
    print(frame.head())

if __name__ == "__main__":
    asyncio.run(main())
```

## 라이브 피드 통합

실시간 캔들 갱신이 필요하면 `CcxtProLiveFeed`를 Seamless provider에 연결하세요.

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

Seamless 런타임은 다음 순서로 데이터를 우선 처리합니다.

1. **캐시/스토리지** – 요청 구간이 이미 QuestDB에 존재하면 즉시 반환합니다.
2. **백필** – 공백 구간이 있으면 CCXT에서 자동 백필 후 QuestDB에 적재합니다.
3. **라이브 피드** – 최신 캔들이 아직 QuestDB에 반영되지 않은 경우 실시간 피드에서 채웁니다.

## 전략/DAG 연동

`StreamInput`과 같이 `HistoryProvider` 인터페이스를 사용하는 노드에는 그대로 Seamless provider를 주입하면 됩니다.

```python
from qmtl.runtime.sdk.nodes.sources import StreamInput

price = StreamInput(
    tags=["btc", "spot"],
    interval="60s",
    period=3600,
    history_provider=provider,
)
```

Seamless provider는 DAG가 요청한 구간을 충족할 때까지 백그라운드 백필과 SLA 측정을 자동으로 수행합니다. `QMTL_SEAMLESS_ARTIFACTS=1`을 설정하면 로컬 개발 중에도 `~/.qmtl_seamless_artifacts/` 하위에 파케이(parquet) 아티팩트가 남아 재현성을 높일 수 있습니다.

## 운영 체크리스트

- **커버리지 점검**: `provider.coverage(node_id=..., interval=...)`를 호출해 QuestDB가 요청 구간을 완전히 보유하고 있는지 주기적으로 확인합니다.
- **모니터링**: `operations/monitoring/seamless_v2.jsonnet` 번들을 배포해 `seamless_sla_deadline_seconds`, `seamless_conformance_flag_total` 대시보드를 활성화합니다.
- **레이트리밋**: 교환소 정책을 위반하면 CCXT가 429를 반환합니다. `CcxtBackfillConfig`의 `min_interval_ms` 또는 Redis 버킷 설정을 조정해 재시도 전 쿨다운을 충분히 확보하세요.
- **에러 재현**: `QMTL_SEAMLESS_COORDINATOR_URL`을 동일하게 설정한 여러 워커는 백필 단일화를 위해 임계구역을 공유합니다. 충돌 시 로그에서 `seamless.backfill.coordinator_*` 이벤트를 확인하세요.

## 문제 해결 FAQ

| 증상 | 원인 | 대응 |
| --- | --- | --- |
| `RuntimeError: ccxt is required ...` | 선택 extras 미설치 | `uv pip install -e .[ccxt]` 재실행 |
| QuestDB 커넥션 실패 | DSN 오타 또는 서버 미기동 | DSN 확인 후 QuestDB 컨테이너/서비스 상태 점검 |
| 백필이 끝나지 않음 | 거래소 API 레이트리밋 초과 | `batch_limit` 축소, `min_interval_ms` 증가, Redis 토큰 버킷 구성 |
| DAG에서 `seamless.sla.downgrade` 경고 | SLA 예산 초과 | `DataAvailabilityStrategy`를 `AUTO_BACKFILL`로 완화하거나 요청 구간 단축 |

## 추가 자료

- `examples/ccxt_seamless_provider.py` – 전체 실행 예제
- [Seamless Migration to v2](seamless_migration_v2.md) – 레거시 히스토리 스택에서의 전환 절차
- [CCXT × QuestDB (IO)](../io/ccxt-questdb.md) – QuestDB 백엔드 세부 설정 및 레이트리밋 전략

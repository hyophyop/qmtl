---
title: "과거 데이터 백필"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 과거 데이터 백필

이 가이드는 전략이 실시간 데이터 처리를 시작하기 전에 노드 캐시를 과거 값으로 채우는 방법을 설명합니다.

## HistoryProvider 구성

`HistoryProvider`는 `(node_id, interval)` 쌍에 대한 과거 데이터를 제공합니다. 
비동기 `fetch(start, end, *, node_id, interval)` 메서드를 구현해야 하며, 
타임스탬프 컬럼 `ts`와 페이로드 필드를 포함하는 `pandas.DataFrame`을 반환합니다. 
메서드 시그니처는 :py:meth:`DataFetcher.fetch`를 반영하며, 프로바이더는 외부 서비스에서 
행을 가져올 때 이를 위임할 수 있습니다. 고급 프로바이더는 선택적으로 비동기 헬퍼를 노출할 수 있습니다:

- `coverage(node_id, interval)` - 기본 저장소에 이미 존재하는 `(start, end)` 타임스탬프 
  범위 목록을 반환합니다. 비동기 코루틴이어야 합니다.
- `fill_missing(start, end, node_id, interval)` - 주어진 범위 내의 갭을 채우도록 
  프로바이더에 지시합니다. 역시 코루틴입니다.
- `ensure_range(start, end, *, node_id, interval)` - 프로바이더가 지원하는 자동 백필을 
  수행합니다. 이것이 있으면 런타임은 수동 커버리지 검사보다 이 헬퍼를 우선합니다.

`coverage()`는 저장소 백엔드에 이미 존재하는 연속적이고 포괄적인 범위를 반환해야 합니다. 
`fill_missing()`이 구현되면 프로바이더는 요청된 범위에서 누락된 타임스탬프에 대한 실제 행을 
삽입할 책임이 있습니다. 러너는 이러한 API를 사용하여 전략에 데이터를 로드하기 전에 
어떤 과거 부분을 가져오거나 생성해야 하는지 결정할 수 있습니다.

어떤 경우에는 프로바이더가 누락된 행을 검색하기 위해 별도의 **DataFetcher** 객체에 의존할 수 있습니다. 
``DataFetcher``는 동일한 프레임 구조를 반환하는 단일 **비동기** ``fetch(start, end, *, node_id, interval)`` 
코루틴을 노출합니다. 프로바이더가 페처 없이 생성되면 ``fill_missing``을 호출할 때 ``RuntimeError``가 발생합니다.

SDK는 QuestDB 인스턴스에서 읽는 `QuestDBHistoryProvider`를 제공합니다:

```python
from qmtl.runtime.sdk import QuestDBHistoryProvider

source = QuestDBHistoryProvider(
    dsn="postgresql://user:pass@localhost:8812/qdb",
)

# with an external fetcher supplying missing rows
# fetcher = MyFetcher()
# source = QuestDBHistoryProvider(
#     dsn="postgresql://user:pass@localhost:8812/qdb",
#     fetcher=fetcher,
# )
```

### 예제 `DataFetcher`

과거 행이 누락되면 로더는 외부 서비스를 쿼리할 수 있습니다.
아래는 Binance에서 캔들스틱을 읽는 최소한의 페처입니다:

```python
import httpx
import pandas as pd
from qmtl.runtime.sdk import DataFetcher

class BinanceFetcher:
    async def fetch(self, start: int, end: int, *, node_id: str, interval: str) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}"
            f"&startTime={start * 1000}&endTime={end * 1000}"
        )
        async with httpx.AsyncClient() as client:
            data = (await client.get(url)).json()
        return pd.DataFrame(
            [
                {"ts": int(r[0] / 1000), "open": float(r[1]), "close": float(r[4])}
                for r in data
            ]
        )

fetcher = BinanceFetcher()
loader = QuestDBHistoryProvider(
    dsn="postgresql://user:pass@localhost:8812/qdb",
    fetcher=fetcher,
)
```

커스텀 프로바이더는 `HistoryProvider`를 구현하거나 동일한 인터페이스를 가진 객체를 제공할 수 있습니다.

함께 제공되는 **EventRecorder**는 처리된 행을 유지합니다. 레코더는 방출된 그대로 각 노드 페이로드를 
수신하는 비동기 ``persist(node_id, interval, timestamp, payload)`` 메서드를 구현해야 합니다. 
프로바이더처럼 레코더도 ``stream.node_id``에서 테이블 이름을 추론하기 위해 ``bind_stream()``을 구현할 수 있습니다.

커스텀 프로바이더나 페처를 빌드할 때는 이러한 메서드 시그니처를 따르고 ``ts`` 컬럼이 있는 
``pandas.DataFrame`` 객체를 반환하기만 하면 됩니다. 서브클래스는 선택 사항입니다 - 프로토콜을 
준수하는 모든 객체가 SDK와 함께 작동합니다.

## 자동 백필 전략

SDK는 :class:`AugmentedHistoryProvider` 파사드를 제공합니다. 이는 내부의
`HistoryBackend`를 감싸며 선택적인 자동 백필 헬퍼들을 조정합니다. 
:class:`AutoBackfillStrategy`를 함께 전달하면, 과거 데이터를 읽기 전에 누락된
범위를 채우는 ``ensure_range`` API가 노출됩니다. 가장 단순한 전략은 기존의
:class:`DataFetcher`에 위임하는 방식입니다.

!!! note
    모든 :class:`HistoryProvider`는 ``ensure_range`` 헬퍼를 노출합니다. 프로바이더가
    이를 오버라이드하지 않으면 기본 구현은 :meth:`fill_missing`으로 프록시합니다.
    따라서 자동 백필 도입 이전에 작성된 어댑터도 변경 없이 동작을 유지합니다.

```python
from qmtl.runtime.sdk import AugmentedHistoryProvider, FetcherBackfillStrategy
from qmtl.runtime.io import QuestDBBackend

backend = QuestDBBackend(dsn="postgresql://user:pass@localhost:8812/qdb")
provider = AugmentedHistoryProvider(
    backend,
    fetcher=my_fetcher,
    auto_backfill=FetcherBackfillStrategy(my_fetcher),
)

# ensure the warmup window is covered before loading
await provider.ensure_range(1700000000, 1700001800, node_id="BTC", interval=60)
frame = await provider.fetch(1700000000, 1700001860, node_id="BTC", interval=60)
```

``FetcherBackfillStrategy``는 커버리지 갭을 계산하고, 각 갭을 페처에 위임하여
정규화한 행을 백엔드에 기록하고 캐시된 커버리지 메타데이터를 갱신합니다. 
외부 API 호출 대신 라이브 버퍼를 활용하는 ``LiveReplayBackfillStrategy`` 같은
대안 전략도 사용할 수 있습니다.

### `StreamInput`에 주입하기

`StreamInput`을 생성할 때 과거 데이터와 이벤트 기록 서비스를 함께 전달할 수 있습니다:

```python
from qmtl.runtime.sdk import (
    StreamInput,
    QuestDBHistoryProvider,
    QuestDBRecorder,
    EventRecorderService,
)

stream = StreamInput(
    interval="60s",
    history_provider=QuestDBHistoryProvider(
        dsn="postgresql://user:pass@localhost:8812/qdb",
        fetcher=fetcher,
    ),
    event_service=EventRecorderService(
        QuestDBRecorder(
            dsn="postgresql://user:pass@localhost:8812/qdb",
        )
    ),
)
```

QuestDB 히스토리 프로바이더는
backwards compatibility) or recorder is created without a ``table`` argument it
automatically uses ``stream.node_id`` as the table name.  Pass ``table="name"``
explicitly to override this behaviour.

``StreamInput`` binds the provider and recorder service during construction and
then treats them as read-only. Attempting to modify ``history_provider`` or
``event_service`` after creation will raise an ``AttributeError``.

## 분산 코디네이터 관측(Observability)

분산 코디네이터에 의존하는 백필 워커는 SDK가 내보내는 구조화된 라이프사이클 로그를 모니터링해야 합니다.
각 성공적인 전이는 `seamless.backfill` 네임스페이스로 로그 항목을 생성합니다:

```text
seamless.backfill.coordinator_claimed {"coordinator_id": "coordinator.local", "lease_key": "nodeA:60:1700:1760:world-1:2024-01-01T00:00:00Z", "node_id": "nodeA", "interval": 60, "batch_start": 1700, "batch_end": 1760, "world": "world-1", "requested_as_of": "2024-01-01T00:00:00Z", "worker": "worker-42", "lease_token": "abc", "lease_until_ms": 2000, "completion_ratio": 0.5}
```

다음의 세 가지 이벤트가 방출됩니다:

- `seamless.backfill.coordinator_claimed` – 워커가 리스를 성공적으로 획득
- `seamless.backfill.coordinator_completed` – 백필 윈도우 완료 및 리스 정상 해제
- `seamless.backfill.coordinator_failed` – 의도적 실패(예: 백필 시도에서 예외 발생)

모든 이벤트는 운영 체크리스트의 필드를 포함합니다:

- **`coordinator_id`** – 분산 코디네이터 URL 호스트에서 파생
- **`lease_key`** – 표준 리스 식별자(`node:interval:start:end:world:requested_as_of`)
- **`node_id`**, **`interval`**, **`batch_start`**, **`batch_end`** – 대시보드를 구동하는 파티션 식별자
- **`world`**, **`requested_as_of`** – 요청 컨텍스트가 월드 거버넌스 메타데이터를 제공할 때 포함
- **`worker`** – `connectors.seamless_worker_id`/`connectors.worker_id`/레거시 env 또는 컨테이너 호스트명에서 채움(프로덕션에서는 일관성 유지를 위해 하나 설정 권장)
- **`lease_token`**, **`lease_until_ms`** – `scripts/lease_recover.py`로 리스 복구 시 유용
- **`completion_ratio`** – Prometheus 게이지와 동일, 리스당 진행률 추적
- **`reason`** – 실패 이벤트에서 리스 중단 사유 주석

Dashboards in `operations/monitoring/seamless_v2.jsonnet` already chart
`backfill_completion_ratio`. Combine those panels with the lifecycle logs above
to understand which worker handled a batch and whether the lease progressed or
required manual recovery.

## 자동 백필 배치 라이프사이클 로그

코디네이터 없이 `DataFetcherAutoBackfiller`가 갭을 복구할 때, 런타임은 배치별 구조화된
라이프사이클을 기록합니다. 동일 네임스페이스에서 노출되어 코디네이터 기반/직접 복구를 대시보드가 상호 참조할 수 있습니다:

```text
seamless.backfill.attempt {"batch_id": "ohlcv:binance:BTC/USDT:60:1700:1760", "attempt": 1, "node_id": "ohlcv:binance:BTC/USDT:60", "interval": 60, "start": 1700, "end": 1760, "source": "storage"}
seamless.backfill.succeeded {"batch_id": "ohlcv:binance:BTC/USDT:60:1700:1760", "attempt": 1, "node_id": "ohlcv:binance:BTC/USDT:60", "interval": 60, "start": 1700, "end": 1760, "source": "storage"}
seamless.backfill.failed {"batch_id": "ohlcv:binance:BTC/USDT:60:1700:1760", "attempt": 2, "node_id": "ohlcv:binance:BTC/USDT:60", "interval": 60, "start": 1700, "end": 1760, "source": "fetcher", "error": "timeout"}
```

- **`batch_id`** – SDK가 생성한 표준 ID `node_id:interval:start:end`(재시도 그룹화 목적)
- **`attempt`** – 재시도 엔진이 제공하는 시도 카운터(1부터 증가)
- **`source`** – 저장소(`fill_missing`/`fetch`) 또는 외부 프로바이더(`fetcher`)
- **`error`** – 실패 이벤트에서 예외 문자열

Dashboards can aggregate on `batch_id` and `attempt` to expose retry rates while
keeping coordinator-driven telemetry untouched.

## 워머프를 위한 히스토리 준비(Priming)

전략을 실행할 때 SDK는 각 `StreamInput`이 `period × interval` 워머프 윈도를 만족할 만큼의
히스토리를 갖추도록 보장합니다. `ensure_range()`를 구현한 프로바이더는 갭 검사 전에 자동 백필을 수행하고,
그렇지 않은 경우 `coverage()` + `fill_missing()` 루프로 폴백합니다.

`Runner.submit`의 모든 모드(backtest/paper/live)는 동일한 워머프 파이프라인을 공유합니다: 프로바이더로
범위를 조정하고 `BackfillEngine`이 노드 캐시에 행을 적재하며, 런타임은 전략 그래프를 통해 이벤트를
리플레이합니다. 이로써 로컬·백테스트·라이브 실행이 동일한 부트스트랩 로직을 수행함이 보장됩니다.

Integrated run (world‑driven):

```python
from qmtl.runtime.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.submit(
    SampleStrategy,
    world="sample_world",
)
```

Offline priming for local testing:

```python
from qmtl.runtime.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.submit(SampleStrategy)
```

During execution the SDK collects cached history and replays it through the
`Pipeline` in timestamp order to initialize downstream nodes. If Ray execution
is enabled, compute functions may run concurrently during this replay phase.

## Monitoring Progress

Backfill operations emit Prometheus metrics via `qmtl.runtime.sdk.metrics`:

- `backfill_jobs_in_progress`: number of active jobs
- `backfill_last_timestamp{node_id,interval}`: latest timestamp successfully backfilled
- `backfill_retry_total{node_id,interval}`: retry attempts
- `backfill_failure_total{node_id,interval}`: total failures

Start the metrics server to scrape these values:

```python
from qmtl.runtime.sdk import metrics

metrics.start_metrics_server(port=8000)
```

Access `http://localhost:8000/metrics` while a backfill is running to observe its progress.

## BackfillEngine Internals

``BackfillEngine`` drives the asynchronous loading of history. Each job is
scheduled via :py:meth:`submit` which creates an ``asyncio`` task. The engine
tracks outstanding tasks in an internal set and :py:meth:`wait` gathers them
before returning. Jobs call ``HistoryProvider.fetch`` and merge the returned
rows into the node cache using
``NodeCache.backfill_bulk``. Completed timestamp ranges are recorded in
``BackfillState`` so subsequent calls can skip already processed data.

```python
from qmtl.runtime.sdk import StreamInput

stream = StreamInput(...)
await stream.load_history(start_ts, end_ts)
```

The ``load_history`` method shown above instantiates ``BackfillEngine``
internally and submits a single job for the configured provider. Failed fetches
are retried up to ``max_retries`` times with a short delay. During execution the
engine emits metrics such as ``backfill_jobs_in_progress``,
``backfill_last_timestamp``, ``backfill_retry_total`` and
``backfill_failure_total``.


{{ nav_links() }}

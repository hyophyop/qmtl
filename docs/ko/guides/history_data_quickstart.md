# 히스토리 데이터 퀵스타트

이 가이드는 QMTL 내부 히스토리 워머프 구현을 거꾸로 따라가지 않고도,
자신의 히스토리 데이터(CSV/Parquet/DB/시뮬레이션)를 전략에 붙이는 방법을
요약합니다. 특히 다음과 같은 전략 레포를 대상으로 합니다.

- 개발 중에는 `Runner.submit(...)` 으로 로컬에서 실행하고,
- 월드 서비스 환경에서는 `Runner.submit(...)` 으로 백테스트/라이브 실험을 돌리는 경우.

새로운 통합에서 권장되는 표면은 **Seamless Data Provider** 레이어입니다.
하위 레벨의 `HistoryProvider` 인터페이스는 여전히 존재하지만,
이제는 고급 확장 포인트로 취급하는 것이 좋습니다.

## 히스토리가 전략으로 들어오는 경로

- 전략은 `StreamInput` 노드를 통해 업스트림 시계열을 선언합니다.
- SDK는 `HistoryWarmupService` 와 `BackfillEngine` 을 사용해
  워머프 시점에 노드 캐시를 채웁니다.
- 전략의 `compute_fn` 은 `CacheView` 를 통해 데이터를 읽습니다.

최근 구조에서는 이 플로우에 데이터를 연결하기 위해
`StreamInput` 에 `SeamlessDataProvider` (또는
`EnhancedQuestDBProvider` 같은 구체 서브클래스)를 물려주는 방식이
가장 자연스럽습니다.

자세한 설계는 다음 문서를 참고하세요.

- [`architecture/seamless_data_provider_v2.md`](../architecture/seamless_data_provider_v2.md)
- [`architecture/seamless_data_provider_v2.md`](../architecture/seamless_data_provider_v2.md)

## Seamless 프로바이더를 스트림에 연결하기

가장 단순한 연결 방법은, `EnhancedQuestDBProvider` 와
`DataFetcher` 구현을 함께 사용하는 것입니다.
`DataFetcher` 는 여러분의 데이터(CSV, Parquet, HTTP, 사내 API 등)를
읽어오는 책임만 가지면 됩니다.

```python
import pandas as pd

from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy
from qmtl.runtime.sdk import StreamInput, ProcessingNode, Strategy, Runner


class ExampleMarketDataFetcher:
    async def fetch(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
    ) -> pd.DataFrame:
        # 실제 구현에서는 여기서 여러분의 데이터 소스를 호출하세요.
        ts = list(range(start, end, interval))
        return pd.DataFrame(
            {
                "ts": ts,
                "price": [100.0 + i * 0.01 for i in range(len(ts))],
            }
        )


class MyStrategy(Strategy):
    def setup(self) -> None:
        provider = EnhancedQuestDBProvider(
            dsn="postgresql://localhost:8812/qmtl",
            table="my_prices",
            fetcher=ExampleMarketDataFetcher(),
            strategy=DataAvailabilityStrategy.SEAMLESS,
        )

        src = StreamInput(
            tags=["price:BTC/USDT:1m"],
            interval="60s",
            period=500,
            history_provider=provider,
        )

        def compute(view):
            series = view[src][60]
            ts, row = series.latest()
            return row["price"]

        node = ProcessingNode(
            input=src,
            compute_fn=compute,
            name="price_node",
            interval="60s",
            period=500,
        )
        self.add_nodes([src, node])
```

핵심 포인트:

- `EnhancedQuestDBProvider` 는 `SeamlessDataProvider` 의 구체 구현으로,
  워머프 레이어가 기대하는 `fetch`, `coverage`, `fill_missing` 메서드를
  이미 제공합니다.
- 여러분의 `DataFetcher` 는 `ts` 컬럼을 포함한 `DataFrame` 만 돌려주면 되고,
  커버리지·자동 백필·정합성 체크는 프로바이더가 맡습니다.
- 전략 쪽 변경은 `StreamInput(history_provider=provider)` 한 줄이면 충분합니다.

더 많은 end‑to‑end 예시는
`examples/seamless_data_provider_examples.py` 를 참고하세요.

QuestDB 없이 파일/노트북 기반 실험만 빠르게 하고 싶다면,
`qmtl.runtime.io.InMemorySeamlessProvider` 를 사용해
DataFrame 또는 CSV 파일을 바로 바인딩할 수도 있습니다.

```python
from qmtl.runtime.io import InMemorySeamlessProvider


class MyStrategy(Strategy):
    def setup(self) -> None:
        provider = InMemorySeamlessProvider()

        src = StreamInput(
            interval="60s",
            period=500,
            tags=["price:BTC/USDT:1m"],
            history_provider=provider,
        )

        # 로컬 CSV 를 한 번 읽어서 src 에 대한 히스토리로 등록합니다.
        provider.register_csv(src, "btc_usdt_1m.csv", ts_col="ts")

        def compute(view):
            series = view[src][60]
            ts, row = series.latest()
            return row["price"]

        node = ProcessingNode(
            input=src,
            compute_fn=compute,
            name="price_node",
            interval="60s",
            period=500,
        )
        self.add_nodes([src, node])
```

## 히스토리 윈도우 제어하기

프로바이더를 연결한 뒤에는, 온라인/오프라인 실행 모두에서
워머프에 사용할 히스토리 윈도우를 제어하고,
기존 전략의 ``setup`` 을 수정하지 않고도 Seamless 프로바이더를
주입할 수 있습니다.

- WorldService / Gateway 실행:

  ```python
  Runner.submit(
      MyStrategy,
      world="my-world",
      gateway_url="http://gateway",
      history_start=1700000000,  # 포함, epoch seconds
      history_end=1700003600,    # 포함 상한, 히스토리 서비스에서 사용
  )
  ```

- 로컬 오프라인 실행:

  ```python
  Runner.submit(
      MyStrategy,
      history_start=1700000000,
      history_end=1700003600,
      # 옵션: 기존 StreamInput 들 중 history_provider 가 없는 노드에
      # Seamless 프로바이더를 자동으로 연결합니다.
      data=my_seamless_provider,
  )
  ```

`history_start` 와 `history_end` 가 모두 `None` 이면, 워머프 서비스는:

- 순수 오프라인 + 프로바이더 없음인 경우에는 작은 기본 윈도우로
  (현재는 `[1, 2]`) 시작하거나,
- 프로바이더 커버리지와 캐시된 스냅샷을 조합하여 적절한 윈도우를
  유추합니다.

## HistoryProvider 는 고급 계약으로 사용하기

하위 레벨의 `HistoryProvider` ABC 는 다음 위치에 존재합니다.

- `qmtl.runtime.sdk.data_io.HistoryProvider`

이 타입은 워머프·백필 서비스의 기반이지만, 일반적인 전략 코드에서는
직접 상속해서 구현할 필요가 **없습니다**.

- `EnhancedQuestDBProvider` 같은 Seamless 계열 프로바이더가 이미 이 계약을
  만족하며, 정합성·SLA·백필 조정 등 더 풍부한 기능을 제공합니다.
- 기존 QuestDB 통합은 필요한 경우 여전히
  `QuestDBHistoryProvider` / `QuestDBLoader` 를 사용할 수 있습니다.

정말로 커스텀 `HistoryProvider` 가 필요한 경우라면,
위 Seamless 설계 문서와 `tests/qmtl/runtime/sdk/` 아래의 테스트
(`test_history_components.py` 등)를 참고하고,
가능하면 워머프 로직을 직접 구현하기보다는 별도의 스토리지 백엔드를
랩핑하는 형태로 구성하는 것을 추천합니다.

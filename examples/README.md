# QMTL Example Strategies

이 디렉터리는 QMTL SDK의 구조적 예제 전략 코드를 제공합니다. 각 예제는 `architecture.md` 문서의 부록 및 주요 설계 예시를 기반으로 하며, 실제 전략 개발 시 참고할 수 있습니다.

Gateway와 DAG manager 실행을 위한 예시 설정은 `qmtl.yml` 파일에 포함되어 있습니다. 환경에 맞게 수정 후 CLI에서 `--config` 인자로 사용할 수 있습니다.

- `general_strategy.py`: 기본 모멘텀 신호 전략
- `tag_query_strategy.py`: 태그 기반 지표 조회 및 다중 노드 조합 예시
- `correlation_strategy.py`: 태그로 선택한 지표들의 상관계수 계산
- `cross_market_lag_strategy.py`: 교차 시장 시차 상관 전략
- `multi_asset_lag_strategy.py`: 다중 자산 시차 상관 전략
- `indicators_strategy.py`: EMA 지표 활용 예제
- `transforms_strategy.py`: rate-of-change 변환 예제
- `generators_example.py`: GARCH 기반 시뮬레이션 데이터 생성
- `extensions_combined_strategy.py`: 확장 모듈 조합 예제
- `ws_metrics_example.py`: WebSocket 클라이언트와 메트릭 활용
- `mode_switch_example.py`: 모드별 실행 방법 예제
- `backfill_history_example.py`: QuestDBLoader를 이용한 캐시 백필 예제
- `metrics_recorder_example.py`: EventRecorder와 메트릭 저장 예제
- `parallel_strategies_example.py`: 멀티 스트래티지 병렬 실행 예제

## 예제 실행 방법

```bash
python examples/general_strategy.py
python examples/tag_query_strategy.py
python examples/correlation_strategy.py
python examples/cross_market_lag_strategy.py
python examples/multi_asset_lag_strategy.py
python examples/indicators_strategy.py
python examples/transforms_strategy.py
python examples/generators_example.py
python examples/extensions_combined_strategy.py
python examples/ws_metrics_example.py
python examples/mode_switch_example.py
python examples/backfill_history_example.py
python examples/metrics_recorder_example.py
python examples/parallel_strategies_example.py
```

백테스트 범위를 지정하려면 `Runner.backtest()` 함수에 시작/종료 타임스탬프를 넘겨줍니다.

```python
from qmtl.sdk import Runner
from examples.multi_asset_lag_strategy import MultiAssetLagStrategy

Runner.backtest(
    MultiAssetLagStrategy,
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-02-01T00:00:00Z",
)
```

> **중요:**
> - QMTL SDK의 모든 예제는 Node의 `compute_fn`이 반드시 read-only `CacheView`(단일 인자)만을 받도록 작성되어 있습니다.
> - 예를 들어, multi-input node의 경우 `compute_fn(view)` 형태로 호출되며, 필요한 입력 데이터는 view에서 키로 조회해야 합니다.
>   ```python
>   def lagged_corr(view):
>       btc = view[btc_price][60].latest()
>       mstr = view[mstr_price][60].latest()
>       ...
>   ```
> - positional argument 방식(`def fn(a, b, ...)`)은 지원하지 않으니, 반드시 단일 인자(CacheView)만 사용하세요.
> - 최신 SDK에서는 ProcessingNode의 input으로 반드시 올바른 업스트림 노드(`StreamInput`, `TagQueryNode` 등)를 연결해야 하며, 필요시 별도의 SourceNode 추상화가 요구될 수 있습니다.
> - 예제 실행 중 "ProcessingNode는 반드시 하나 이상의 업스트림을 가져야 합니다" 등의 에러가 발생할 경우, SDK의 input 연결 시그니처와 예제 코드를 반드시 확인하세요.

# QMTL Example Strategies

이 디렉터리는 QMTL SDK의 구조적 예제 전략 코드를 제공합니다. 각 예제는 `architecture.md` 문서의 부록 및 주요 설계 예시를 기반으로 하며, 실제 전략 개발 시 참고할 수 있습니다.

- `general_strategy.py`: 기본 모멘텀 신호 전략
- `tag_query_strategy.py`: 태그 기반 지표 조회 및 다중 노드 조합 예시
- `correlation_strategy.py`: 태그로 선택한 지표들의 상관계수 계산
- `cross_market_lag_strategy.py`: 교차 시장 시차 상관 전략

## 예제 실행 방법

```bash
python examples/general_strategy.py
python examples/tag_query_strategy.py
python examples/correlation_strategy.py
python examples/cross_market_lag_strategy.py
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

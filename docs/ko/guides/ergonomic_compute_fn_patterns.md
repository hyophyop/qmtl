# compute_fn 헬퍼 활용 가이드 (Ergonomic compute_fn patterns)

`CacheView`는 계산 함수가 필요로 하는 모든 입력을 포함하지만, 윈도우 슬라이싱·컬럼 검증·다중 업스트림 정렬을 매번 수동으로 처리하면 코드가 금방 장황해집니다. 본 가이드는 SDK에 추가된 헬퍼 API를 이용해 `compute_fn`을 선언적으로 작성하는 방법을 정리합니다.

## 헬퍼 계층이 제공하는 것

- **윈도우 단위 조회**: `view.window(node, interval, length)`는 원하는 길이만큼 바로 잘라 줍니다. DataFrame이 필요하면 `view.as_frame(..., window=...)`을 사용하세요.
- **컬럼 존재성 검증**: `CacheFrame.validate_columns([...])`는 필수 컬럼 누락 시 즉시 예외를 던져 조기 실패를 보장합니다.
- **다중 업스트림 정렬**: `view.align_frames([(node, interval), ...], window=...)`는 공통 타임스탬프에 맞춰 데이터프레임을 교집합으로 정렬합니다.

## 1) 윈도우 조회와 프레임 변환

```python
from qmtl.runtime.sdk import StreamInput
from qmtl.runtime.sdk.cache_view import CacheView

price = StreamInput(interval="1m", period=30)
view: CacheView = ...

# 마지막 10개만 가져오기
latest_price = view.window(price, 60, 10)

# DataFrame으로 바로 변환 + 윈도우 적용
price_frame = view.as_frame(price, 60, window=10, columns=["close"]).validate_columns(["close"])
```

## 2) 컬럼 검증과 파생 계산

`CacheFrame`에서 필요한 컬럼을 검증한 뒤, `returns`/`pct_change` 등 헬퍼를 그대로 활용할 수 있습니다.

```python
momentum = price_frame.returns(window=1, dropna=False)
signal = (momentum > 0).astype(int)
```

## 3) 다중 입력 노드 정렬

여러 업스트림을 한 번에 묶어야 할 때는 `align_frames`가 교집합 인덱스를 유지해 줍니다.

```python
aligned = view.align_frames([(price_node, 60), (signal_node, 60)], window=20)
price_frame, signal_frame = aligned

close = price_frame.validate_columns(["close"]).frame["close"]
flag = signal_frame.validate_columns(["flag"]).frame["flag"]
merged = close.to_frame("close").assign(flag=flag.values)
```

## 4) compute_fn 전체 예시

아래 예시는 **윈도우 → 컬럼 검증 → 다중 입력 정렬** 순서를 모두 헬퍼로 처리하는 최소 패턴입니다.

```python
from qmtl.runtime.sdk import Node

price_node = Node(...)
signal_node = Node(...)


def compute(view):
    price_frame, signal_frame = view.align_frames(
        [(price_node, 60), (signal_node, 60)],
        window=12,
    )

    returns = price_frame.validate_columns(["close"]).returns(window=1, dropna=False)
    flags = signal_frame.validate_columns(["flag"]).frame["flag"]

    return returns.to_frame("close_return").assign(flag=flags.values)
```

헬퍼 계층을 사용하면 `compute_fn`이 값 병합과 정렬에 집중할 수 있으며, 테스트 또한 동일한 헬퍼를 호출하는 방식으로 간결하게 작성할 수 있습니다.

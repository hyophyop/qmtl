# CacheView 헬퍼 빠르게 쓰기

`CacheView.window()`와 `CacheWindow`는 노드별 캐시 스냅샷을 바로 `DataFrame` / `Series` 로 변환해 주는 얇은 헬퍼입니다. 베타 팩토리 이슈(#1645)에서 지적된 “뷰 → 리스트 → DataFrame → 컬럼 검사” 보일러플레이트를 몇 줄로 줄여 줍니다.

## 기본 사용법

```python
from qmtl.runtime.sdk import CacheView

def compute(view: CacheView):
    price_win = view.window("prices", 60, count=50)
    price_win.require_columns(["close", "volume"])

    frame = price_win.as_frame()  # ts, close, volume 컬럼을 포함
    closes = price_win.to_series("close")
    returns = closes.pct_change().dropna()
```

- `window(node, interval, count=N)` 은 최근 N개만 슬라이스합니다. `count=None`이면 전체 창을 사용합니다.
- 페이로드가 스칼라인 경우 `as_frame()`은 `value` 컬럼을 만듭니다.
- `require_columns([...])` 는 누락 컬럼을 명시적으로 알립니다.

## 다중 입력 정렬 예시

```python
def compute(view: CacheView):
    asset = view.window("asset_prices", 60, count=120).to_series("close")
    bench = view.window("benchmark", 60, count=120).to_series("close")

    aligned = (
        pd.concat({"asset": asset, "bench": bench}, axis=1)
        .dropna()
        .pct_change()
        .dropna()
    )
    cov = aligned.cov().loc["asset", "bench"]
    var = aligned["bench"].var()
    beta = cov / var if var else None
    return {"beta": beta}
```

- 시계열 인덱스는 자동으로 `ts`(기본) 기반으로 맞춰집니다.
- 필요한 경우 `to_series(..., dropna=False)` 로 정렬 전 빈 구간을 남겨둘 수 있습니다.

## 스칼라·빈 창 처리

- 창이 비어 있으면 `as_frame()`은 컬럼만 있는 빈 DataFrame을 반환하고, `latest()`는 `None`을 반환합니다.
- `count=0` 같은 요청도 빈 창으로 안전하게 처리됩니다.

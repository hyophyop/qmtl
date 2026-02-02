# 멀티자산 팩터 DAG 패턴

여러 심볼을 동시에 다루는 팩터 DAG를 만들 때 쓸 수 있는 권장 데이터 형태와 노드 배치를 정리합니다. HFT 베타 팩토리 피드백(#1651)에서 나온 “멀티심볼 정렬/결합 보일러플레이트”를 줄이는 것이 목표입니다.

## 1. 데이터 형태 선택

- **Tall(권장, 기본)**: 심볼을 컬럼으로 두지 않고 각 행에 `symbol` 필드를 포함한 형태. 예) `{"ts": ..., "symbol": "BTCUSDT", "close": 100}`.  
  - 장점: StreamInput/노드가 심볼별로 간단해지고, 새 심볼 추가 시 DAG 구조를 덜 바꿉니다.
  - 단점: 팩터 노드에서 피벗/집계를 한 번 수행해야 합니다.
- **Wide(소형 유니버스 한정)**: 한 행에 여러 심볼 필드를 포함. 예) `{"ts": ..., "close": {"BTC": 100, "ETH": 10}}` 또는 `{"close_BTC": 100, "close_ETH": 10}`.  
  - 장점: 피벗 없이 바로 연산 가능.  
  - 단점: 스냅샷 크기가 빠르게 커지고, 심볼 추가가 코드/스키마 변경을 강제합니다.

### 권장
- 시세/체결 입력은 **심볼별 StreamInput**(tall)로 두고, 팩터 노드에서 필요한 구간만 피벗/정렬해 사용합니다.
- 소수(≈5개 미만) 심볼만 다루는 실험에서는 wide도 가능하지만, 확장성을 우선하면 tall을 기본으로 삼으세요.

## 2. CacheView 패턴

`CacheView.window()`와 `CacheWindow` 헬퍼를 사용하면 리스트→DataFrame 피벗 보일러플레이트를 줄일 수 있습니다. (참고: [cacheview_helpers.md](./cacheview_helpers.md))

```python
from qmtl.runtime.sdk import CacheView
import numpy as np
import polars as pl

UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

def compute(view: CacheView):
    frames = []
    for sym in UNIVERSE:
        win = view.window(f"px:{sym}", 60, count=200)
        # tall 형태: 컬럼에 symbol을 추가해 병합
        frame = win.as_frame()
        if frame.is_empty():
            continue
        frame = frame.with_columns(pl.lit(sym).alias("symbol"))
        frames.append(frame.select(["ts", "symbol", "close"]))

    if not frames:
        return None

    tall = pl.concat(frames).sort("ts")
    wide = tall.pivot(values="close", index="ts", columns="symbol")
    returns = wide.select(pl.all().pct_change()).drop_nulls()

    # 예시: 벤치마크(컬럼 baseline) 대비 단순 베타
    if "baseline" not in returns.columns:
        return None
    cov = np.cov(returns.to_numpy(), rowvar=False)
    cols = returns.columns
    idx = cols.index("baseline")
    var_b = cov[idx, idx]
    betas = (
        {col: cov[cols.index(col), idx] / var_b for col in cols}
        if var_b
        else None
    )
    return {"beta": betas}
```

- `count=`로 창 크기를 제한해 스냅샷 부피를 관리하세요.
- 심볼 누락 시 빈 프레임이 섞여도 실패하지 않도록 방어 코드를 두는 것이 좋습니다.

## 3. DAG 배치 예시(개념)

- StreamInput: `px:{symbol}` (시세), 필요 시 `vol:{symbol}` 등 추가
- 팩터 노드:
  - 1단계: 가격/거래량을 수집해 피벗/정렬 (`CacheView.window` 활용)
  - 2단계: 크로스섹션 팩터 계산(베타, 스프레드, 바스켓 등)
  - 3단계: 필요 시 심볼별 신호로 분해하거나 포트폴리오/리스크 노드로 전달
- Store/Artifacts: 교차 심볼 피벗 결과가 크다면, 중간 결과를 퍼블리시/아티팩트로 남겨 반복 계산을 줄일 수 있습니다.

## 4. 히스토리/백필 주의점

- 멀티심볼 팩터는 **공통 시간축 정렬**이 중요합니다. `history_start`/`history_end`를 지정하거나, SeamlessDataProvider가 각 심볼 커버리지를 맞춰 내려주도록 설정하세요.
- 창이 비어 있는 심볼은 팩터에서 제외하거나, `dropna=False`로 정렬 후 결측을 보전하는 등 정책을 명확히 하세요.

## 5. 체크리스트

- [ ] 입력은 가능하면 tall 형태로 유지하고 심볼 추가/삭제가 DAG 변화 없이 가능한가?
- [ ] `CacheView.window(..., count=...)`로 창 길이를 명시했는가?
- [ ] 결측/심볼 누락 시 방어 코드가 있는가?
- [ ] 팩터 출력 스키마가 심볼 키를 어떻게 표현하는지(딕셔너리/행렬) 문서화했는가?

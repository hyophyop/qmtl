# SDK: opt-in auto-derive returns/PnL 제안서

## 0. As‑Is / To‑Be 요약

- As‑Is
  - 이 문서는 Runner/ValidationPipeline 관점에서 returns/pnl 자동 파생의 여러 옵션을 탐색하는 초안으로, 실제 런타임은 여전히 `strategy.returns/equity/pnl` 기반 수동 제공에 의존하고 있습니다.
  - 설계된 `auto_derive_returns`/`auto_returns` 플래그는 구현되지 않았고, auto_returns 통합 방향은 `auto_returns_unified_design.md`에서 재정의되었습니다.
- To‑Be
  - 통합 설계(`auto_returns_unified_design.md`)가 구현되면, 본 문서는 비교/역사적 참고용으로 축소하거나 deprecated로 전환합니다.
  - 상단 As‑Is 섹션에서 “현재 구현은 없다”는 점을 명시적으로 유지해, 독자가 실 구현과 설계를 혼동하지 않도록 합니다.

> **관련 이슈**: [hyophyop/qmtl#1723](https://github.com/hyophyop/qmtl/issues/1723)
> **상태**: 초안
> **작성일**: 2025-11-29

## 요약

`Runner.submit`/`ValidationPipeline`에서 전략이 `returns`/`equity`/`pnl`을 명시하지 않아도 가격 데이터에서 선택적으로 자동 파생할 수 있는 경로를 추가합니다.

## 현재 문제점

### 증상
- `strategy.returns`, `strategy.equity`, `strategy.pnl`이 모두 없으면 `auto_validate`가 다음 에러로 실패:
  ```
  "strategy produced no returns; auto-validation cannot proceed"
  ```
- 라이브 피드 기반 샌드박스 제출에서 단순 전략들이 리턴 미설정 때문에 모두 거절됨

### 현재 returns 추출 로직

`_extract_returns_from_strategy` 함수 (`qmtl/runtime/sdk/submit.py`, `validation_pipeline.py`)가 다음 순서로 시도:

1. `strategy.returns` 속성
2. `strategy.equity` → returns로 변환 (pct_change)
3. `strategy.pnl` 속성

세 가지 모두 없으면 빈 리스트 반환 → `auto_validate=True`일 때 거절

## 제안 해결책

### 1. 새로운 파라미터 추가

```python
# Runner.submit / submit_async 시그니처 확장
async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    # ... 기존 파라미터들
    auto_derive_returns: bool | str | None = None,  # 새 옵션
    returns_field: str = "close",  # 파생 시 사용할 필드
) -> SubmitResult:
```

| `auto_derive_returns` 값 | 동작 |
|---|---|
| `None` (기본값) | 기존 동작 유지 - 명시적 returns/equity/pnl 필요 |
| `True` 또는 `"price"` | 첫 번째 `StreamInput` 노드의 `close` 필드에서 pct_change 파생 |
| `"<node_name>"` | 지정된 이름의 노드에서 파생 |

### 2. Returns 파생 헬퍼 함수

새 모듈 `qmtl/runtime/sdk/returns_derive.py`:

```python
"""전략 노드에서 returns 시리즈를 자동 파생하는 헬퍼."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .strategy import Strategy

logger = logging.getLogger(__name__)


def derive_returns_from_price_node(
    strategy: "Strategy",
    *,
    node_name: str | None = None,
    field: str = "close",
    min_samples: int = 2,
) -> list[float]:
    """전략의 price 노드에서 returns 시리즈를 파생합니다.
    
    Parameters
    ----------
    strategy : Strategy
        returns를 파생할 전략 인스턴스
    node_name : str, optional
        특정 노드 이름 지정. None이면 첫 번째 StreamInput 사용
    field : str
        가격 필드명 (기본: "close")
    min_samples : int
        최소 필요 샘플 수 (기본: 2)
        
    Returns
    -------
    list[float]
        파생된 returns 시리즈 (pct_change)
    """
    from .nodes.wiring import StreamInput
    
    # 타겟 노드 찾기
    target_node = None
    for node in strategy.nodes:
        if node_name and node.name == node_name:
            target_node = node
            break
        if node_name is None and isinstance(node, StreamInput):
            target_node = node
            break
    
    if not target_node:
        logger.debug("No suitable price node found for returns derivation")
        return []
    
    # 캐시에서 데이터 추출
    cache_data = target_node.cache._snapshot().get(target_node.node_id, {})
    interval_data = cache_data.get(target_node.interval, [])
    
    if len(interval_data) < min_samples:
        logger.debug(
            "Insufficient data for returns derivation: %d samples (min: %d)",
            len(interval_data),
            min_samples,
        )
        return []
    
    # field 값 추출 후 pct_change 계산
    prices = []
    for ts, payload in interval_data:
        if isinstance(payload, dict) and field in payload:
            prices.append(float(payload[field]))
        elif hasattr(payload, field):
            prices.append(float(getattr(payload, field)))
    
    if len(prices) < min_samples:
        logger.debug(
            "Insufficient price values extracted: %d (min: %d)",
            len(prices),
            min_samples,
        )
        return []
    
    # pct_change 계산
    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] != 0:
            returns.append((prices[i] - prices[i-1]) / prices[i-1])
        else:
            returns.append(0.0)
    
    logger.info(
        "Auto-derived %d returns from node '%s' field '%s'",
        len(returns),
        target_node.name,
        field,
    )
    return returns


__all__ = ["derive_returns_from_price_node"]
```

### 3. `_extract_returns_from_strategy` 확장

```python
def _extract_returns_from_strategy(
    strategy: "Strategy",
    *,
    auto_derive: bool | str | None = None,
    returns_field: str = "close",
) -> list[float]:
    """Extract returns from a strategy instance if available.
    
    Parameters
    ----------
    strategy : Strategy
        전략 인스턴스
    auto_derive : bool | str | None
        None: 기존 동작 (명시적 returns만)
        True/"price": 첫 번째 StreamInput에서 파생
        "<node_name>": 지정 노드에서 파생
    returns_field : str
        auto_derive 시 사용할 가격 필드 (기본: "close")
    """
    # 1. 명시적 returns/equity/pnl 우선
    returns_attr = getattr(strategy, "returns", None)
    if returns_attr:
        return list(returns_attr)

    equity_attr = getattr(strategy, "equity", None)
    if equity_attr:
        equity = list(equity_attr)
        if len(equity) >= 2:
            returns = []
            for i in range(1, len(equity)):
                if equity[i - 1] != 0:
                    returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
                else:
                    returns.append(0.0)
            return returns

    pnl_attr = getattr(strategy, "pnl", None)
    if pnl_attr:
        return list(pnl_attr)

    # 2. opt-in auto-derive fallback
    if auto_derive:
        from .returns_derive import derive_returns_from_price_node
        
        node_name = None if auto_derive is True or auto_derive == "price" else auto_derive
        derived = derive_returns_from_price_node(
            strategy,
            node_name=node_name,
            field=returns_field,
        )
        if derived:
            return derived

    return []
```

### 4. ValidationPipeline 확장

```python
class ValidationPipeline:
    def __init__(
        self,
        *,
        preset: PolicyPreset | str = PolicyPreset.SANDBOX,
        policy: Policy | None = None,
        world_id: str = "__default__",
        existing_strategies: list[StrategyInfo] | None = None,
        existing_returns: dict[str, Sequence[float]] | None = None,
        world_sharpe: float | None = None,
        # 새 파라미터
        auto_derive_returns: bool | str | None = None,
        returns_field: str = "close",
    ) -> None:
        # ...
        self.auto_derive_returns = auto_derive_returns
        self.returns_field = returns_field
    
    async def validate(
        self,
        strategy: "Strategy",
        *,
        returns: Sequence[float] | None = None,
        risk_free_rate: float = 0.0,
        transaction_cost: float = 0.0,
    ) -> ValidationResult:
        # ...
        if returns is None:
            returns = self._extract_returns_from_strategy(
                strategy,
                auto_derive=self.auto_derive_returns,
                returns_field=self.returns_field,
            )
        # ...
```

### 5. SubmitResult 메타데이터 확장

```python
@dataclass
class SubmitResult:
    # ... 기존 필드들
    returns_source: str | None = None  # "explicit", "derived:close", "derived:mid_price" 등
```

## 사용 예시

```python
from qmtl.runtime.sdk import Runner, Mode

# 기존 방식 (변경 없음) - 명시적 returns 필요
result = Runner.submit(MyStrategy, world="paper")

# 새 옵션: 자동 파생 활성화 (smoke test/demo용)
result = Runner.submit(
    MyStrategy,
    world="paper",
    auto_derive_returns=True,  # 첫 번째 StreamInput의 close 사용
)

# 특정 노드/필드 지정
result = Runner.submit(
    MyStrategy,
    world="paper",
    auto_derive_returns="my_price_node",
    returns_field="mid_price",
)

# ValidationPipeline 직접 사용
pipeline = ValidationPipeline(
    preset="sandbox",
    auto_derive_returns=True,
)
result = await pipeline.validate(strategy)
```

## 설계 원칙

| 원칙 | 준수 방법 |
|---|---|
| **Opt-in** | 기본값 `None`으로 기존 동작 유지, 명시적 활성화 필요 |
| **명시적 우선** | `strategy.returns/equity/pnl`이 있으면 auto-derive 무시 |
| **유연성** | 노드명/필드명 지정 가능 |
| **역호환성** | 기존 API 시그니처 유지 (새 파라미터는 optional) |
| **SoC** | `returns_derive.py` 별도 모듈로 분리 |
| **투명성** | `returns_source` 메타데이터로 파생 여부 추적 가능 |

## 고려사항

### 경고 및 로깅
- auto-derive 사용 시 INFO 레벨로 "returns auto-derived from node X field Y" 로깅
- 데이터 부족 시 DEBUG 레벨로 원인 기록

### 제한사항
- auto-derive된 returns는 단순 pct_change이므로:
  - 포지션 사이징, 거래 비용, 슬리피지 미반영
  - 실전 전략은 명시적 returns/pnl 사용 권장
- 문서화에 "smoke test/demo 용도" 명시 필요

### 향후 확장
- `returns_transform` 파라미터로 커스텀 변환 함수 지원 가능
- 여러 노드에서 weighted returns 파생 지원 가능

## 구현 체크리스트

- [ ] `qmtl/runtime/sdk/returns_derive.py` 신규 모듈 생성
- [ ] `submit.py`의 `_extract_returns_from_strategy` 확장
- [ ] `submit_async` 시그니처에 `auto_derive_returns`, `returns_field` 추가
- [ ] `ValidationPipeline` 생성자에 동일 파라미터 추가
- [ ] `SubmitResult`에 `returns_source` 필드 추가
- [ ] 단위 테스트 작성
- [ ] 문서 업데이트

## 관련 링크

- [hyophyop/qmtl#1723](https://github.com/hyophyop/qmtl/issues/1723) - 원본 이슈
- [hyophyop/hft-factory-strategies#9](https://github.com/hyophyop/hft-factory-strategies/issues/9) - 실제 PnL 검증 에픽

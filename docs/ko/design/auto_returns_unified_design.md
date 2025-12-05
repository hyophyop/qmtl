---
title: "SDK 자동 returns 파생 통합 설계안"
tags: [design, returns, validation, sr, sdk]
author: "QMTL Team"
last_modified: 2025-11-30
status: draft
related_issue: "hyophyop/qmtl#1723"
---

# SDK 자동 returns 파생 통합 설계안

## 0. As‑Is / To‑Be 요약

- As‑Is
  - Runner.submit/submit_async는 `auto_returns` 옵션을 통해 price/equity 시계열에서 returns를 파생할 수 있으며, 명시적 `returns`나 `strategy.returns/equity/pnl`이 있으면 우선 사용한다.
  - SR 템플릿(`build_expression_strategy`, `build_strategy_from_dag_spec`)으로 생성된 전략은 기본적으로 returns를 만들지 않기 때문에, `auto_returns` 구성을 전달하지 않으면 여전히 Runner.submit + auto‑validate 흐름과 직접 연결되지 않는다.
- To‑Be
  - Runner.submit/submit_async 전처리 단계에 `auto_returns` 옵션을 추가하고,  
    Strategy warm‑up/replay 결과에서 가격 스트림을 찾아 pct_change/log_return 기반 returns를 파생하는 헬퍼(`returns_derive.py`)를 도입합니다.
  - ValidationPipeline 계약은 “이미 계산된 returns만 입력받는다”로 유지하고, auto_returns는 Runner 전처리에만 머무르게 하며, SR 템플릿은 `auto_returns` 설정을 통해 Core Loop(제출→평가→활성화)에 자연스럽게 편입됩니다.

> **관련 이슈**: [hyophyop/qmtl#1723](https://github.com/hyophyop/qmtl/issues/1723)  
> **통합 대상 문서**:
> - [`auto_derive_returns_proposal.md`](./auto_derive_returns_proposal.md) — SDK 전반 설계
> - [`sr_auto_returns_integration_sketch.md`](./sr_auto_returns_integration_sketch.md) — SR 경로 스케치
> - [`auto_returns_proposals_comparison.md`](./auto_returns_proposals_comparison.md) — 두 설계 비교

이 문서는 기존 두 설계안의 장점을 조합하고 단점을 보완한 **통합 설계안**입니다.

---

## 1. 설계 원칙

### 1.1 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **Opt-in** | 기본값은 기존 동작 유지, 명시적 활성화 필요 |
| **명시적 우선** | `strategy.returns/equity/pnl`이 있으면 auto-derive 무시 |
| **계층 분리** | auto-returns는 Runner.submit 전처리에 한정, ValidationPipeline 계약 유지 |
| **확장 가능** | 단순 bool에서 구조화된 Config로 점진적 확장 가능 |
| **관측성** | 파생 여부와 출처를 항상 추적 가능 |

### 1.2 계층 책임 분리

```
┌─────────────────────────────────────────────────────────────────┐
│                     Runner.submit / submit_async                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  1. 명시적 returns 확인 (strategy.returns/equity/pnl)     │  │
│  │  2. auto_returns 옵션이 활성화되면 → ReturnsDeriver 호출  │  │
│  │  3. 파생된 returns + returns_source 메타데이터 생성       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│                    [returns: list[float]]                       │
│                    [returns_source: str]                        │
│                              ↓                                   │
├─────────────────────────────────────────────────────────────────┤
│                     ValidationPipeline                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  • 기존 계약 유지: "이미 계산된 returns를 입력받음"       │  │
│  │  • auto_returns 파라미터 없음 (침투 방지)                 │  │
│  │  • returns_source는 결과 메타데이터로만 전달              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
├─────────────────────────────────────────────────────────────────┤
│                     WorldService / Gateway                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  • 기존 계약 유지                                         │  │
│  │  • returns_source 기반 정책 적용 가능 (예: derived 제한)  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**핵심 결정**: ValidationPipeline에 `auto_derive_returns` 파라미터를 추가하지 않음. 이는 계약 표면적을 넓히지 않고, Runner.submit에서 모든 returns 결정을 완료한 뒤 "이미 계산된 returns"만 전달하는 깔끔한 설계를 유지합니다.

---

## 2. API 설계

### 2.1 설정 모델: `AutoReturnsConfig`

단순 `bool | str` 대신 **구조화된 설정 객체**를 사용하여 확장성을 확보합니다.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Callable, Sequence


@dataclass(frozen=True)
class AutoReturnsConfig:
    """자동 returns 파생 설정.
    
    Parameters
    ----------
    node : str | None
        타겟 노드 이름. None이면 첫 번째 StreamInput 사용.
        예: "price", "ccxt:BTCUSDT", "my_price_node"
    field : str
        가격 필드명. 기본값 "close".
        예: "close", "mid", "price", "vwap"
    method : Literal["pct_change", "log_return"]
        returns 계산 방식. 기본값 "pct_change".
    min_samples : int
        최소 필요 샘플 수. 미달 시 파생 실패.
    transform : Callable[[Sequence[float]], Sequence[float]] | None
        선택적 후처리 함수 (예: 거래 비용 조정).
    
    Examples
    --------
    >>> # 가장 단순한 사용
    >>> AutoReturnsConfig()
    
    >>> # 특정 노드/필드 지정
    >>> AutoReturnsConfig(node="btc_price", field="mid")
    
    >>> # log return 사용
    >>> AutoReturnsConfig(method="log_return", min_samples=30)
    """
    node: str | None = None
    field: str = "close"
    method: Literal["pct_change", "log_return"] = "pct_change"
    min_samples: int = 2
    transform: Callable[[Sequence[float]], Sequence[float]] | None = None

    def __bool__(self) -> bool:
        """Config 인스턴스는 항상 truthy."""
        return True


# 편의 상수
AUTO_RETURNS_DEFAULT = AutoReturnsConfig()
AUTO_RETURNS_LOG = AutoReturnsConfig(method="log_return")
```

### 2.2 타입 별칭

```python
from typing import Union

# auto_returns 파라미터 타입
AutoReturnsOption = Union[bool, str, AutoReturnsConfig, None]
```

### 2.3 Runner.submit 시그니처

```python
async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    world: str | None = None,
    mode: Mode | str = Mode.BACKTEST,
    preset: str | None = None,
    preset_mode: str | None = None,
    preset_version: str | None = None,
    preset_overrides: dict[str, float] | None = None,
    returns: Sequence[float] | None = None,
    auto_validate: bool = True,
    # === 새 파라미터 ===
    auto_returns: AutoReturnsOption = None,
) -> SubmitResult:
    """전략을 제출하고 검증합니다.
    
    Parameters
    ----------
    auto_returns : bool | str | AutoReturnsConfig | None
        자동 returns 파생 옵션.
        
        - None (기본값): 기존 동작 유지, 명시적 returns만 사용
        - True: 첫 번째 StreamInput의 close 필드에서 pct_change 파생
        - "<node_name>": 지정된 노드의 close 필드에서 파생
        - AutoReturnsConfig(...): 상세 설정으로 파생
        
        명시적 `returns` 인자 또는 `strategy.returns/equity/pnl`이
        있으면 이 옵션은 무시됩니다.
    
    Notes
    -----
    auto_returns로 파생된 returns는 단순 pct_change이므로 포지션 사이징,
    거래 비용, 슬리피지를 반영하지 않습니다. 실전 전략은 명시적
    returns/pnl 사용을 권장합니다.
    """
    ...
```

---

## 3. 파생 로직

### 3.1 모듈 구조

```
qmtl/runtime/sdk/
├── returns_derive.py      # 새 모듈: 파생 로직
├── submit.py              # 기존: auto_returns 옵션 처리 추가
└── validation_pipeline.py # 변경 없음
```

### 3.2 `returns_derive.py` 구현

```python
"""전략 노드에서 returns 시리즈를 자동 파생하는 헬퍼.

이 모듈은 Runner.submit의 전처리 단계에서 사용되며,
ValidationPipeline에는 직접 노출되지 않습니다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Sequence

if TYPE_CHECKING:
    from .strategy import Strategy

logger = logging.getLogger(__name__)


@dataclass
class DeriveResult:
    """Returns 파생 결과."""
    
    returns: list[float]
    source: str  # "derived:close", "derived:mid:log_return" 등
    node_name: str | None
    sample_count: int
    
    @property
    def success(self) -> bool:
        return len(self.returns) > 0


def derive_returns(
    strategy: "Strategy",
    *,
    node: str | None = None,
    field: str = "close",
    method: Literal["pct_change", "log_return"] = "pct_change",
    min_samples: int = 2,
) -> DeriveResult:
    """전략의 price 노드에서 returns 시리즈를 파생합니다.
    
    Parameters
    ----------
    strategy : Strategy
        returns를 파생할 전략 인스턴스
    node : str | None
        특정 노드 이름 지정. None이면 첫 번째 StreamInput 사용
    field : str
        가격 필드명 (기본: "close")
    method : {"pct_change", "log_return"}
        returns 계산 방식
    min_samples : int
        최소 필요 샘플 수 (기본: 2)
        
    Returns
    -------
    DeriveResult
        파생 결과 (성공 여부, returns, 메타데이터)
    """
    from .nodes.wiring import StreamInput
    
    empty_result = DeriveResult(
        returns=[],
        source=f"derived:{field}:{method}",
        node_name=None,
        sample_count=0,
    )
    
    # 1. 타겟 노드 찾기
    target_node = None
    for n in strategy.nodes:
        if node and n.name == node:
            target_node = n
            break
        if node is None and isinstance(n, StreamInput):
            target_node = n
            break
    
    if not target_node:
        logger.debug(
            "No suitable price node found for returns derivation "
            "(requested: %s)",
            node or "first StreamInput",
        )
        return empty_result
    
    # 2. 캐시에서 데이터 추출
    try:
        cache_data = target_node.cache._snapshot().get(target_node.node_id, {})
        interval_data = cache_data.get(target_node.interval, [])
    except Exception as e:
        logger.debug("Cache access failed: %s", e)
        return empty_result
    
    if len(interval_data) < min_samples:
        logger.debug(
            "Insufficient data for returns derivation: %d samples (min: %d)",
            len(interval_data),
            min_samples,
        )
        return empty_result._replace(
            node_name=target_node.name,
            sample_count=len(interval_data),
        )
    
    # 3. 가격 값 추출
    prices: list[float] = []
    for ts, payload in interval_data:
        value = None
        if isinstance(payload, dict) and field in payload:
            value = payload[field]
        elif hasattr(payload, field):
            value = getattr(payload, field)
        
        if value is not None:
            try:
                prices.append(float(value))
            except (TypeError, ValueError):
                continue
    
    if len(prices) < min_samples:
        logger.debug(
            "Insufficient price values extracted from field '%s': %d (min: %d)",
            field,
            len(prices),
            min_samples,
        )
        return empty_result._replace(
            node_name=target_node.name,
            sample_count=len(prices),
        )
    
    # 4. Returns 계산
    returns: list[float] = []
    for i in range(1, len(prices)):
        prev, curr = prices[i - 1], prices[i]
        if prev == 0:
            returns.append(0.0)
        elif method == "log_return":
            returns.append(math.log(curr / prev))
        else:  # pct_change
            returns.append((curr - prev) / prev)
    
    source = f"derived:{field}"
    if method != "pct_change":
        source += f":{method}"
    
    logger.info(
        "Auto-derived %d returns from node '%s' field '%s' (method=%s)",
        len(returns),
        target_node.name,
        field,
        method,
    )
    
    return DeriveResult(
        returns=returns,
        source=source,
        node_name=target_node.name,
        sample_count=len(prices),
    )


def normalize_auto_returns_option(
    option: "AutoReturnsOption",
) -> "AutoReturnsConfig | None":
    """다양한 형태의 auto_returns 옵션을 AutoReturnsConfig로 정규화."""
    from . import AutoReturnsConfig
    
    if option is None or option is False:
        return None
    if option is True:
        return AutoReturnsConfig()
    if isinstance(option, str):
        return AutoReturnsConfig(node=option if option != "price" else None)
    if isinstance(option, AutoReturnsConfig):
        return option
    
    raise TypeError(
        f"auto_returns must be bool, str, AutoReturnsConfig, or None, "
        f"got {type(option).__name__}"
    )


__all__ = [
    "DeriveResult",
    "derive_returns",
    "normalize_auto_returns_option",
]
```

### 3.3 `submit.py` 수정 (개념)

```python
async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    # ... 기존 파라미터들
    auto_returns: AutoReturnsOption = None,
) -> SubmitResult:
    # ... 기존 초기화 로직 ...
    
    # === returns 결정 로직 (우선순위) ===
    returns_source: str | None = None
    
    # 1. 명시적 returns 인자
    if returns is not None:
        backtest_returns = list(returns)
        returns_source = "explicit:argument"
    else:
        # 2. strategy 속성에서 추출 (기존 로직)
        backtest_returns = _extract_returns_from_strategy(strategy)
        if backtest_returns:
            returns_source = "explicit:strategy"
    
    # 3. auto_returns fallback (opt-in)
    if not backtest_returns and auto_returns:
        from .returns_derive import derive_returns, normalize_auto_returns_option
        
        config = normalize_auto_returns_option(auto_returns)
        if config:
            result = derive_returns(
                strategy,
                node=config.node,
                field=config.field,
                method=config.method,
                min_samples=config.min_samples,
            )
            if result.success:
                backtest_returns = result.returns
                if config.transform:
                    backtest_returns = list(config.transform(backtest_returns))
                returns_source = result.source
            else:
                # 파생 실패 시 improvement_hints에 추가
                logger.warning(
                    "auto_returns enabled but derivation failed for node=%s, field=%s",
                    config.node,
                    config.field,
                )
    
    # === 이후 기존 로직 (ValidationPipeline 호출 등) ===
    if auto_validate:
        if not backtest_returns:
            return SubmitResult(
                # ... 기존 rejection 로직 ...
                improvement_hints=[
                    "Ensure your strategy populates returns/equity/pnl during warmup",
                    "Pass pre-computed returns via Runner.submit(..., returns=...)",
                    "Enable auto_returns=True to derive from price data (smoke/demo only)",
                ],
            )
        
        validation_pipeline = ValidationPipeline(...)
        validation_result = await validation_pipeline.validate(
            strategy,
            returns=backtest_returns,  # 이미 결정된 returns 전달
        )
    
    # SubmitResult에 returns_source 포함
    return SubmitResult(
        # ... 기존 필드들 ...
        returns_source=returns_source,
    )
```

---

## 4. SubmitResult 확장

```python
@dataclass
class SubmitResult:
    """전략 제출 결과."""
    
    strategy_id: str
    status: str  # "active", "rejected", "pending"
    world: str
    mode: Mode
    rejection_reason: str | None = None
    improvement_hints: list[str] = field(default_factory=list)
    metrics: StrategyMetrics = field(default_factory=StrategyMetrics)
    strategy: "Strategy" | None = None
    contribution: float | None = None
    weight: float | None = None
    rank: int | None = None
    
    # === 새 필드 ===
    returns_source: str | None = None
    """Returns 출처.
    
    가능한 값:
    - "explicit:argument" — returns 인자로 직접 전달됨
    - "explicit:strategy" — strategy.returns/equity/pnl에서 추출됨
    - "derived:close" — auto_returns로 close 필드에서 파생됨
    - "derived:mid:log_return" — mid 필드에서 log return으로 파생됨
    - None — returns 없음 (rejected 상태일 때)
    """
```

---

## 5. SR 통합

SR(Strategy Recommendation) 경로에서는 `AutoReturnsConfig`를 활용하여 **표준화된 returns 파생 규칙**을 적용합니다.

### 5.1 SR 템플릿 통합

```python
# qmtl/integrations/sr/strategy_template.py

from qmtl.runtime.sdk import AutoReturnsConfig

# SR 전략용 표준 auto_returns 설정
SR_AUTO_RETURNS_CONFIG = AutoReturnsConfig(
    node=None,      # 첫 번째 StreamInput (표준 price 노드)
    field="close",
    method="pct_change",
    min_samples=30,  # SR 평가에 필요한 최소 샘플
)


def build_strategy_from_dag_spec(
    dag_spec: Any,
    *,
    history_provider: Any | None,
    sr_engine: str | None = "pysr",
    auto_returns: AutoReturnsOption = SR_AUTO_RETURNS_CONFIG,  # SR 기본값
    # ...
) -> type[Strategy]:
    """DAG 스펙에서 전략 클래스를 생성합니다."""
    ...
```

### 5.2 SR 제출 흐름

```python
# SR 엔진에서 후보 전략 생성 후 제출
from qmtl.runtime.sdk import Runner
from qmtl.integrations.sr import build_strategy_from_dag_spec, SR_AUTO_RETURNS_CONFIG

# 1. DAG 스펙에서 전략 생성
StrategyClass = build_strategy_from_dag_spec(
    dag_spec,
    history_provider=seamless_provider,
    sr_engine="pysr",
)

# 2. 제출 (SR 표준 auto_returns 설정 사용)
result = await Runner.submit_async(
    StrategyClass,
    world="sandbox",
    auto_returns=SR_AUTO_RETURNS_CONFIG,
)

# 3. 결과 확인
print(result.returns_source)  # "derived:close"
```

### 5.3 SR 집단 내 비교 가능성

동일한 `AutoReturnsConfig`를 사용하면 SR 후보군 내에서 **지표 비교가 공정하고 일관**됩니다:

- 모든 후보가 동일한 노드/필드/계산 방식으로 returns를 파생
- fitness 비교가 동일한 기준으로 이루어짐
- 세대별 개선을 추적할 수 있음

---

## 6. 선순환 설계

### 6.1 단계별 피드백 루프

```
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: 빠른 On-ramp (auto_returns=True)                      │
│  ├─ 목적: 지표 확인, 빠른 탐색/필터링                            │
│  ├─ 대상: smoke test, demo, SR 초기 후보                        │
│  └─ 제한: derived returns, 실제 PnL과 차이 있음                  │
├─────────────────────────────────────────────────────────────────┤
│  Stage 2: 검증 강화 (explicit returns)                          │
│  ├─ 목적: 실제 거래 로직 반영, 고품질 지표                       │
│  ├─ 대상: 유망 후보, 실전 테스트 대상                            │
│  └─ 요구: strategy.returns/equity/pnl 명시                      │
├─────────────────────────────────────────────────────────────────┤
│  Stage 3: 실전 배포 (explicit + strict policy)                  │
│  ├─ 목적: 라이브 환경 운영                                       │
│  ├─ 대상: 검증 완료 전략                                         │
│  └─ 정책: derived returns 거부, 명시적 returns만 허용            │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 World 정책 예시

```yaml
# sandbox world - auto_returns 허용
worlds:
  sandbox:
    validation:
      allow_derived_returns: true
      min_return_samples: 30
    
  # paper world - 경고만
  paper:
    validation:
      allow_derived_returns: true
      warn_on_derived_returns: true
      min_return_samples: 100
    
  # live world - 명시적 returns만 허용
  live:
    validation:
      allow_derived_returns: false
      min_return_samples: 252
```

---

## 7. 구현 체크리스트

### Phase 1: 핵심 구현

- [ ] `AutoReturnsConfig` 데이터클래스 정의 (`qmtl/runtime/sdk/__init__.py`)
- [ ] `qmtl/runtime/sdk/returns_derive.py` 모듈 생성
  - [ ] `DeriveResult` 데이터클래스
  - [ ] `derive_returns()` 함수
  - [ ] `normalize_auto_returns_option()` 함수
- [ ] `submit.py` 수정
  - [ ] `submit_async` 시그니처에 `auto_returns` 추가
  - [ ] returns 결정 로직에 auto_returns fallback 추가
  - [ ] `returns_source` 메타데이터 생성
- [ ] `SubmitResult`에 `returns_source` 필드 추가
- [ ] 단위 테스트 작성
  - [ ] `test_returns_derive.py` — 파생 로직 테스트
  - [ ] `test_submit_auto_returns.py` — 통합 테스트

### Phase 2: SR 통합

- [ ] `SR_AUTO_RETURNS_CONFIG` 상수 정의
- [ ] `build_strategy_from_dag_spec`에 `auto_returns` 파라미터 추가
- [ ] SR 템플릿 E2E 테스트

### Phase 3: 정책 및 관측성

- [ ] World 정책에 `allow_derived_returns` 옵션 추가
- [ ] 메트릭 노출: derived_returns_ratio, auto_returns_failure_rate
- [ ] 문서 업데이트

---

## 8. 기존 설계안 대비 개선점

| 측면 | `auto_derive_returns_proposal` | `sr_integration_sketch` | **통합안** |
|------|-------------------------------|------------------------|-----------|
| API 확장성 | `bool \| str` — 제한적 | `AutoReturnsConfig` 스케치 | **`AutoReturnsConfig` 구체화** |
| 계층 분리 | ValidationPipeline까지 침투 | Runner 한정 권장 | **Runner 한정 확정** |
| SR 통합 | 미언급 | 초점 | **표준 Config 상수** |
| 관측성 | `returns_source` 제안 | 미상세 | **DeriveResult + returns_source** |
| 선순환 | 일반 on-ramp | SR 비교 가능성 | **단계별 정책 설계** |

---

## 9. 위험 및 완화

| 위험 | 영향 | 완화 방안 |
|------|------|---------|
| derived returns에 대한 과신 | 실제 PnL과 괴리된 최적화 | `returns_source` 명시, World 정책으로 실전 환경 제한 |
| 캐시 접근 실패 | 파생 불가 | graceful degradation, 명확한 에러 메시지 |
| SR 외 사용자 혼란 | API 복잡도 증가 | 단순 `auto_returns=True` 지원, 문서화 |

---

## 10. 관련 링크

- [hyophyop/qmtl#1723](https://github.com/hyophyop/qmtl/issues/1723) — 원본 이슈
- [hyophyop/hft-factory-strategies#9](https://github.com/hyophyop/hft-factory-strategies/issues/9) — 실제 PnL 검증 에픽
- [`sr_integration_proposal.md`](./sr_integration_proposal.md) — SR 통합 설계

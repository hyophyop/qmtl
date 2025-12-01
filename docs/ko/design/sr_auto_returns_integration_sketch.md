---
title: "SR × Runner.submit 자동 수익률(returns) 파생 스케치"
tags: [design, sr, validation, returns]
author: "QMTL Team"
last_modified: 2025-11-29
status: draft
---

# SR × Runner.submit 자동 수익률(returns) 파생 스케치

## 0. As‑Is / To‑Be 요약

- As‑Is
  - 이 문서는 SR 템플릿과 Runner.submit을 auto_returns 옵션으로 엮는 경량 스케치를 제공하지만, 현재 Runner/WS/Seamless 경로에는 auto_returns 구현이 없고 SR 전략은 returns를 직접 만들지 않는 한 Runner.submit + auto‑validate 흐름과 연결되지 않습니다.
- To‑Be
  - `auto_returns_unified_design.md`에서 정의한 통합 설계가 구현되면, SR 템플릿은 `auto_returns` 설정을 통해 Core Loop(제출→평가→활성화)에 자연스럽게 편입됩니다.
  - 이 문서는 SR 관점에서의 추가 고려사항(데이터 일관성, validation 샘플, expression_key dedup)을 보완 문서로 유지하며, 상단 As‑Is 섹션에서 “구현 없는 설계 초안”임을 분명히 합니다.

> **관련 이슈**: [hyophyop/qmtl#1723](https://github.com/hyophyop/qmtl/issues/1723)  
> **관련 설계 문서**: [`auto_derive_returns_proposal.md`](./auto_derive_returns_proposal.md), [`sr_integration_proposal.md`](./sr_integration_proposal.md)

이 문서는 SR(Strategy Recommendation)·피드 기반 전략에서, 전략이 `returns`/`equity`/`pnl`을 직접 채우지 않아도 **Runner.submit이 opt-in으로 최소 returns 시리즈를 파생**해 주는 경량 통합 스케치를 정리한 임시 메모입니다.

## 1. 배경

- 현재 Runner.submit/submit_async는 다음 순서로 수익률을 해석합니다.
  1. 호출자가 `returns` 인자를 직접 넘기면 그대로 사용
  2. 전략 인스턴스의 `returns` → `equity`(pct_change) → `pnl` 속성을 `_extract_returns_from_strategy`로 조회
  3. 모두 비어 있으면 `auto_validate=True`일 때 `"strategy produced no returns; auto-validation cannot proceed"`로 거절
- SR/피드 기반 단순 전략은 가격 스트림만 읽고 의사결정하는 경우가 많아, **데이터는 충분하지만 returns 배선 보일러플레이트**가 불필요하게 요구됩니다.
- `docs/ko/design/auto_derive_returns_proposal.md`는 SDK 전반에서의 opt-in auto-derive 설계를 다루고, 이 문서는 그중 **SR 경로에서 Runner.submit과 어떻게 이어 붙일지**에 초점을 둡니다.

## 2. 목표

- 기본 동작은 그대로 두고, **명시적으로 opt-in한 전략**에 한해서만 가격 시계열에서 최소 returns 시리즈를 파생합니다.
- ValidationPipeline/WorldService는 여전히 “returns를 이미 넘겨받는다”는 계약을 유지하고, auto-returns는 **Runner.submit 쪽 전처리 레이어**로만 둡니다.
- SR·피드 기반 경량 전략은 간단한 설정만 추가해도 auto-validation을 통과하게 하고, 실전 전략은 기존처럼 명시적 `returns`/`equity`/`pnl`을 우선 사용합니다.

## 3. Runner.submit API 스케치

Runner.submit/submit_async 시그니처에 opt-in 옵션을 추가하는 방향을 제안합니다.

```python
async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    # ... existing params ...
    auto_returns: bool | "AutoReturnsConfig" | None = None,
) -> SubmitResult: ...
```

- `auto_returns=None` (기본값): 기존 동작 유지, auto-derive 시도 없음.
- `auto_returns=True`: “가장 단순한 디폴트” (예: 첫 price 노드 `close` pct_change) 전략으로 한 번 시도.
- `auto_returns=AutoReturnsConfig(...)`: 노드/필드/계산 방식을 명시적으로 제어.

개념적 설정 객체 스케치는 다음과 같습니다.

```python
@dataclass
class AutoReturnsConfig:
    node: str | None = None           # 예: "price", "ccxt:BTCUSDT" 등
    field: str = "close"              # 예: "close", "price", "mid"
    method: Literal["pct_change", "log_return"] = "pct_change"
    min_length: int | None = None     # 너무 짧으면 실패로 간주
```

SR 경로에서는 ExpressionDagBuilder/Seamless Provider가 정의한 **표준 price 노드 이름/필드 규약**을 이 Config에 반영해 재사용할 수 있습니다.

## 4. 우선순위 및 실패 처리

예상 우선순위는 다음과 같이 유지합니다.

1. 호출자가 `returns` 인자를 직접 넘긴 경우: 그대로 사용하고 auto-derive는 시도하지 않습니다.
2. `returns` 인자가 없으면 기존 `_extract_returns_from_strategy` 동작:
   - `strategy.returns` → `strategy.equity` → `strategy.pnl` 순으로 조회.
3. 위 단계로도 `backtest_returns`가 비어 있고 `auto_returns`가 truthy인 경우에만 **auto-derive 경로**를 시도합니다.
4. auto-derive 이후에도 returns가 없거나 `min_length` 미만이면, 현재와 동일하게 `"no returns; auto-validation cannot proceed"`로 reject하되,
   - improvement_hints에 `"auto_returns enabled but no usable price series found for node=..., field=..."` 등의 메시지를 추가합니다.

이렇게 하면:

- **명시적 returns/equity/pnl이 항상 우선**이며,
- auto-derive는 opt-in fallback으로만 동작합니다.

## 5. 파생 헬퍼 유틸리티

Runner.submit 내부에 직접 가격 처리 로직을 두지 않고, SDK 유틸리티로 분리하는 방향을 가정합니다.

```python
def derive_returns_from_price(
    strategy: Strategy,
    *,
    node: str | None = None,
    field: str = "close",
    method: Literal["pct_change", "log_return"] = "pct_change",
) -> list[float]:
    ...
```

- 구현 위치 예시: `qmtl/runtime/sdk/metrics.py` 또는 유사 모듈.
- 역할:
  - 전략이 보유한 view/노드 스냅샷(예: Seamless StreamInput 출력)을 통해 지정된 `node/field`의 가격 시퀀스를 조회.
  - `method`에 따라 단순 pct_change 또는 log return 계산.
  - SR 통합에서는 Expression DAG/Seamless Provider가 제공하는 **표준 price 노드**를 그대로 재사용.

상세한 노드 탐색/캐시 접근 방식은 `auto_derive_returns_proposal.md`에 정의된 `derive_returns_from_price_node` 방향과 정렬하는 것을 전제로 합니다.

## 6. SR 통합 시 고려 사항

- SR 경로(예: `sr_integration_proposal.md`)에서는 이미 Seamless Data Provider와 `expression_dag_spec`/`data_spec`에 의존합니다.
- 이 문서의 auto-returns 스케치는 다음과 같이 SR 설계와 결합됩니다.
  - ExpressionDagBuilder가 생성하는 DAG에 **표준 price 노드 이름/필드**를 포함.
  - SR 전략 템플릿이 Runner.submit 호출 시, 해당 노드/필드에 맞는 `AutoReturnsConfig` 또는 `auto_returns=True`를 함께 넘김.
- 그 결과:
  - PySR 등 SR 엔진이 만든 **단순 가격 기반 전략**도 별도의 returns 배선 없이 auto-validation을 통과할 수 있고,
  - 복잡한 전략이나 실전 전략은 기존처럼 명시적 `returns`/`equity`/`pnl` 제공을 통해 세밀한 제어를 유지합니다.

향후 실제 구현 시에는:

- `auto_derive_returns_proposal.md`의 보다 상세한 API/유틸 설계와 이 문서의 SR 통합 스케치를 병합해,
- Runner.submit/ValidationPipeline/WorldService의 계약을 깨지 않는 선에서 최종 API를 확정해야 합니다.

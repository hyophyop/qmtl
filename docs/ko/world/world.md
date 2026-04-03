---
title: "QMTL 월드 — 전략 생애주기 관리 사양"
tags: [world, strategy]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL 월드(World) — 전략 생애주기 관리 사양 v1

본 문서는 월드(World)를 QMTL의 전략 생애주기 관리 단위로 정의하는 상위 계약입니다. 세부 런타임/API/운영 문서는 분리되었고, 이 페이지는 월드가 무엇을 소유하며 어떤 결정 흐름으로 Runner와 주문 경로를 제어하는지에 집중합니다.

> **용어:** QMTL의 공식 용어는 항상 `World`입니다. 과거 `Realm` 제안은 채택되지 않았습니다.

- 기준 문서:
  - [QMTL 규범 아키텍처](../architecture/architecture.md)
  - [Gateway](../architecture/gateway.md)
  - [DAG Manager](../architecture/dag-manager.md)
  - [WorldService](../architecture/worldservice.md)
- 저장소 경계:
  - `qmtl/`에는 재사용 가능한 기능만 둡니다.
  - 전략(알파) 구현은 저장소 루트 `strategies/`에 둡니다.
- 데이터 핸들러 기본값:
  - `SeamlessDataProvider`가 히스토리/백필 경로의 기본값입니다.

## 0. Core Loop 관점 요약

월드는 Core Loop를 다음 네 단계로 조직합니다.

1. 전략 제출 → 월드 바인딩 (`Runner.submit(..., world=...)`, WSB)
2. 월드 평가 (`/worlds/{id}/evaluate`) → 결정 엔벌로프
3. 활성화/게이팅 (`/worlds/{id}/activation`, 이벤트 스트림) → 주문 경로 제어
4. 자본 배분 (`/allocations`, `/rebalancing/*`) → world/strategy allocations

이 문서는 이 네 단계의 계약을 설명하고, 세부 엔드포인트·운영 절차는 하위 문서에 위임합니다.

## 1. 목적과 비범위

목적

- World를 전략 상위 추상화로 두고 정책(WorldPolicy)에 따라 평가·선정·실행 모드를 제어합니다.
- 데이터 통화성, 표본 충분성, 성과 임계값, 상관/리스크 제약, 히스테리시스를 조합해 승격/강등 결정을 내립니다.
- Runner는 단일 진입점으로 실행되고, Gateway/DAG Manager/SDK 메트릭을 그대로 재사용합니다.

비범위

- 신규 분산 스케줄러, 신규 메시지 브로커, 신규 그래프 모델은 도입하지 않습니다.
- 전략 프로세스 생성/종료와 같은 배포 자동화는 별도 운영 도구의 책임입니다.

## 2. 핵심 개념 및 데이터

- **World**: 전략 묶음의 실행 경계. 예: `crypto_mom_1h`
- **WorldPolicy(vN)**: 버전드 YAML 정책 스냅샷
- **StrategyInstance**: `(strategy, params, side, world)` 단위 인스턴스
- **Activation Table**: 월드별 활성 전략과 가중치를 담는 경량 캐시
- **Audit Log**: 평가 입력, Top-K 결정, 2-Phase apply 결과

권장 저장 위치

- 정책 정의: `config/worlds/<world_id>.yml`
- 활성 테이블: Redis `world:<world_id>:active`
- 감사 로그/정책 버전: Gateway/WorldService가 사용하는 DB 확장

## 3. 상태·전환(최소 사양)

- Runner는 실행 모드를 직접 선택하지 않고 월드 결정에 따릅니다.
- 월드 관점 운영 상태는 `evaluating`, `applying`, `steady`만 추적합니다.
- 2-Phase apply 요지:
  1. Freeze/Drain
  2. Switch
  3. Unfreeze
- 모든 단계는 idempotent `run_id`로 추적하고 롤백 포인트를 남깁니다.

노드/큐/태그 세부 상태는 DAG Manager와 SDK 계약을 그대로 사용합니다.

## 4. 평가 정책 DSL(간결형)

YAML 기반으로 `Gates -> Score -> Constraints -> Top-K -> Hysteresis` 다섯 단계를 최소 표현으로 제공합니다.

```yaml
world: crypto_mom_1h
version: 1

data_currency:
  max_lag: 5m
  min_history: 60d
  bar_alignment: exchange_calendar

selection:
  gates:
    and:
      - sample_days >= 30
      - trades_60d >= 40
      - sharpe_mid >= 0.60
      - max_dd_120d <= 0.25
  score: "sharpe_mid + 0.1*winrate_long - 0.2*ulcer_mid"
  topk:
    total: 8
    by_side: { long: 5, short: 3 }
  constraints:
    correlation:
      max_pairwise: 0.8
    exposure:
      gross_budget: { long: 0.60, short: 0.40 }
      max_leverage: 3.0
      sector_cap: { per_sector: 0.30 }
  hysteresis:
    promote_after: 2
    demote_after: 2
    min_dwell: 3h

campaign:
  backtest:
    window: 180d
  paper:
    window: 30d
  common:
    min_sample_days: 30
    min_trades_total: 100

position_policy:
  on_promote: flat_then_enable
  on_demote: disable_then_flat
```

정책 엔진 세부는 [정책 엔진](policy_engine.md)에 위임합니다.

## 5. 결정 알고리즘(요지)

결정 순서는 `데이터 통화성 -> 게이트 -> 점수 -> 제약 -> Top-K -> 히스테리시스` 입니다.

```python
def decide_initial_mode(now, data_end, max_lag):
    return "active" if (now - data_end) <= max_lag else "validate"

def gate_metrics(m, policy):
    if m.sample_days < policy.min_sample_days:
        return "insufficient"
    if m.trades_60d < policy.min_trades:
        return "insufficient"
    return "pass" if eval_expr(policy.gates, m) else "fail"

def apply_hysteresis(prev, checks, h):
    dwell_ok = time_in_state(prev) >= h.min_dwell
    if checks.consecutive_pass >= h.promote_after and dwell_ok:
        return "PROMOTE"
    if checks.consecutive_fail >= h.demote_after and dwell_ok:
        return "DEMOTE"
    return "HOLD"
```

## 6. 통합 지점

- Runner: 월드 결정에 따르는 단일 진입점
- Gateway: 제출/상태/큐 조회와 world API 프록시
- DAG Manager: NodeID/토픽/태그 해석 SSOT
- Metrics: SDK/Gateway/DAG Manager의 기존 Prometheus 메트릭 재사용

### 6.1 World-first runtime integration

Runner/CLI 실행 표면, 폴백 규칙, 활성화 상호작용은 [월드 런타임 통합](world_runtime_integration.md)에서 정의합니다.

<a id="62-데이터-preset-onramp"></a>
### 6.2 데이터 preset on-ramp

월드는 data preset의 SSOT이며, Runner/CLI는 world + preset만으로 Seamless 인스턴스를 자동 구성해야 합니다. 세부 스키마와 preset 맵은 [월드 데이터 preset 계약](world_data_preset.md)에 정리합니다.

### 6.3 Tag/interval ↔ 큐 라우팅

TagQueryNode, Gateway `/queues/by_tag`, DAG Manager topic namespace는 동일한 태그/interval 규약을 공유해야 합니다. 상세는 [월드 데이터 preset 계약](world_data_preset.md)의 라우팅 섹션을 따릅니다.

## 7. 주문 게이트(OrderGate)

- 형태: SDK 공용 `OrderGateNode` 또는 동등한 어댑터
- 위치: 주문/브로커리지 노드 직전
- 기본 정책: 활성화가 명시적으로 열려 있지 않으면 차단
- 2-Phase apply에서는 Freeze/Drain이 최우선

세부 엔벌로프와 fail-closed 규칙은 [월드 주문 게이트](world_order_gate.md)에 위임합니다.

## 8. 경계·원칙

- 재사용 우선: Gateway, DAG Manager, SDK Runner, 기존 메트릭을 가능한 그대로 사용합니다.
- 단순성 우선: 월드 자체 FSM을 최소화하고 핵심은 평가 → 활성화 → 게이트로 유지합니다.
- 보수적 기본값: 히스테리시스, 쿨다운, 리스크 컷은 기본 켜짐 상태를 권장합니다.
- 저장소 경계 준수: 공용 기능은 `qmtl/`, 전략 구현은 `strategies/`에 둡니다.

## 9. 상세 문서

- [월드 런타임 통합](world_runtime_integration.md)
- [월드 데이터 preset 계약](world_data_preset.md)
- [월드 주문 게이트](world_order_gate.md)
- [월드 롤아웃 및 운영](world_rollout_and_ops.md)
- [월드 레지스트리](world_registry.md)
- [World API 레퍼런스](../reference/api_world.md)
- [월드 이벤트 스트림 런타임](../architecture/world_eventstream_runtime.md)
- [중앙집중형 리밸런싱 정책](rebalancing.md)
- [정책 엔진](policy_engine.md)

{{ nav_links() }}

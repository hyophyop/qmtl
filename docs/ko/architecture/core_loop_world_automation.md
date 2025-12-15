---
title: "Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스"
tags: [architecture, core-loop, worldservice, campaign, governance]
author: "QMTL Team"
last_modified: 2025-12-15
---

{{ nav_links() }}

# Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스

!!! abstract "요약"
    Core Loop의 목표는 “전략 + 월드만 제출하면, 월드가 단계(backtest → paper(dryrun) → live)를 관리”하는 것이다.  
    호출자는 `Runner.submit(strategy, world=...)`만 사용하고, 단계/승격/거버넌스는 **WorldService 정책**이 결정한다.  
    평가 입력(특히 실현 리턴/포트폴리오 스냅샷)은 `risk_signal_hub`를 SSOT로 고정한다.

관련 문서:
- QMTL 전체 아키텍처: [architecture/architecture.md](architecture.md)
- WorldService 아키텍처: [architecture/worldservice.md](worldservice.md)
- Risk Signal Hub: [architecture/risk_signal_hub.md](risk_signal_hub.md)
- 평가 런/메트릭 API(icebox, 참고용): [design/worldservice_evaluation_runs_and_metrics_api.md](../design/icebox/worldservice_evaluation_runs_and_metrics_api.md)
- (아카이브) 단계별 작업 로드맵: [archive/core_loop_world_roadmap.md](../archive/core_loop_world_roadmap.md)

---

## 1. 시스템 경계와 데이터 흐름

```mermaid
flowchart LR
    U[User/CI] -->|Runner.submit(strategy, world)| SDK[SDK/Runner]
    SDK -->|submit payload| GW[Gateway]
    GW -->|/worlds/{id}/evaluate\n/activation\n/apply| WS[WorldService]
    GW -->|POST /risk-hub| HUB[(Risk Signal Hub)]
    HUB -->|risk_snapshot_updated\nControlBus event| WS
    SCHED[Scheduler/Loop\n(qmtl or external)] -->|POST /worlds/{id}/campaign/tick\n(+ execute recommended actions)| WS
```

- **Runner/SDK**: 사용자 표면. 제출은 `Runner.submit(strategy, world=...)`로 수렴한다.
- **WorldService**: 월드 정책 SSOT. 평가 런(Evaluation Run), 캠페인 상태, 승격 후보/거버넌스 결정을 소유한다.
- **Risk Signal Hub**: 포트폴리오/리스크/실현 리턴 스냅샷 SSOT. “저장 전용”이며 계산 책임은 프로듀서에 둔다.
- **Scheduler/Loop**: Phase 4의 경량 오케스트레이션. 외부 스케줄러 또는 `qmtl world campaign-loop` 같은 내부 루프가 `tick` 기반으로 실행한다.

---

## 2. Core Loop 계약(SSOT)

- **client-side `mode`는 없다.**
  - 실행 단계/승격은 월드 정책과 WS가 결정한다.
  - SDK/Runner는 WS가 제공하는 결정(envelope)을 입력으로만 취급한다.
- **Default-safe(보수적 기본값)**:
  - WS 결정이 없거나 stale이면 compute-only(backtest)로 강등한다.
  - `allow_live=false`일 때는 어떤 경우에도 live 전환(activation/apply)을 허용하지 않는다.

---

## 3. Evaluation Run과 메트릭 소싱(Phase 2–4 핵심)

WorldService는 “제출/평가/검증/승격 후보”를 **Evaluation Run**으로 추적한다.

- 평가 엔드포인트(개념):
  - `POST /worlds/{id}/evaluate` (단일 전략 평가)
  - `POST /worlds/{id}/evaluate-cohort` (캠페인/후보군 평가)
- `run_id`는 멱등성/재실행 식별자다(동일 `run_id`로 업데이트가 가능해야 함).
- **metrics는 클라이언트에서 조립하지 않아도 된다.**
  - 요청의 `metrics`가 비어 있으면 WS가 소싱 전략으로 채운 뒤 평가한다.
  - 우선순위(요약):
    - 최근 evaluation run의 metrics 재사용(stage 일치 우선) →
    - `risk_signal_hub` 스냅샷 기반 보강(공분산/스트레스/실현 리턴 ref/inline) →
    - (paper/live/shadow/dryrun) `realized_returns`가 있으면 리턴 시계열에서 v1 core 성과 지표를 계산해 채움

!!! note "`realized_returns` 기반 ‘시간 경과 지표 갱신’"
    외부 엔진 없이도, “일정 주기로 `/evaluate` 호출”만으로 paper/live 단계의 성과 지표(sharpe/max_drawdown/effective_history_years 등)가 갱신된다.  
    단, returns 자체를 생산하는 책임(집계/정합성)은 여전히 프로듀서(예: Gateway)에 있다.

---

## 4. 캠페인 오케스트레이션(Phase 4)

캠페인은 “관찰 윈도우를 채우고 승격 후보를 산출하는 루프”다.

- 정책(요약):
  - `campaign.backtest.window`, `campaign.paper.window` 등 최소 관찰 기간/표본 조건을 정책으로 고정한다.
- 상태(요약):
  - `phase: backtest_campaign | paper_campaign | live_campaign`
  - phase별 윈도우 진행률, 관찰된 핵심 지표, 승격 가능/불가능 사유를 노출한다.
- `tick`(경량 계약):
  - `POST /worlds/{id}/campaign/tick`은 **사이드이펙트 없이** “다음 액션 추천”을 반환한다.
  - 추천 액션에는 `idempotency_key`, `suggested_run_id`, `suggested_body`(템플릿; metrics 포함하지 않음)를 포함한다.

---

## 5. live 승격 거버넌스(Phase 5)

live 승격은 기본적으로 “운영/거버넌스” 단계이며, 월드별로 정책으로 고정한다.

- 정책 예시:
  - `governance.live_promotion.mode: disabled | manual_approval | auto_apply`
- 불변조건:
  - `auto_apply`로 설정하더라도, Phase 4의 paper(dryrun) 관찰과 Phase 5의 validation 게이트는 **생략되지 않는다**.
- fail-closed(필수):
  - `risk_signal_hub` 스냅샷이 missing/expired/stale이면 승격은 차단되고, 차단 사유를 후보/리포트에 남긴다.

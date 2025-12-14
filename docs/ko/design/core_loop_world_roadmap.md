---
title: "Core Loop × WorldService 단계별 고도화 로드맵"
tags: [design, roadmap, core-loop, worldservice]
author: "QMTL Team"
last_modified: 2025-12-08
status: draft
---

# Core Loop × WorldService 단계별 고도화 로드맵

이 문서는 Core Loop를 **“전략+월드만 제출하면, 월드가 모드·단계·캠페인을 관리하는 구조”**로 수렴시키기 위한 **실행 로드맵**이다.  
아키텍처 문서(`architecture/architecture.md`)가 전체 그림을 잡는다면, 이 문서는 **구현 작업자가 “지금 무엇을, 어떤 순서로 바꾸는지”를 잃지 않게 해 주는 북극성 가이드** 역할을 한다.

핵심 목표는 다음 한 줄로 요약된다.

> **사용자는 전략 로직과 월드만 지정하고, “backtest → 검증 → paper → (선택적) live” 단계는 월드 정책과 WorldService가 관리한다.**

여기서 제안하는 단계들은 **강한 순서 제약**이 있다. 가능한 한 아래 순서대로 적용해야 한다.

- Phase 0–1: **계약 정리·WS‑우선 모드 결정** (기존 기능 강화, 행동 변화 최소)
- Phase 2–3: **Evaluation Run 1급 개념화, world‑first 제출 UX** (API/모델 변화)
- Phase 4–5: **캠페인 오케스트레이션, 검증 단계 고도화** (전략 생애주기 자동화 수준 확대)

## 0. 사전 합의: 지향점과 비범위

### 0.1 지향점

- 모드는 **사용자가 직접 선택하는 플래그**가 아니라,  
  **월드 정책과 WorldService가 결정하는 상태**에 가깝게 재정의한다.
- “검증/리스크/exit에 필요한 입력 데이터”는 WorldService가 직접 계산하기보다,  
  **스냅샷 SSOT(`risk_signal_hub`)를 통해 버전 고정(ref/hash/as_of) 형태로 공유**하는 방향을 지향한다.  
  (관련: [Risk Signal Hub 아키텍처](../architecture/risk_signal_hub.md))
- Core Loop의 표면은 다음 흐름을 기준으로 설계한다.

```text
전략 작성 → Runner.submit(strategy, world)
          → (월드 안에서 backtest/검증/승격 후보 선정)
          → paper/live 후보군 관리
          → 운영자가 live 적용 여부를 결정
```

- 소규모 조직에서도 **기술로 리스크를 통제**할 수 있도록,  
  **월드의 “검증” 단계를 고도화**하고, live 승격은 기본값으로 **명시적인 apply/운영자 승인**을 요구하되 월드별 거버넌스 정책으로 opt‑in 자동 승격도 허용한다.

### 0.2 비범위

- WorldService 안에 **대규모 백테스트 엔진을 새로 만들지 않는다.**
  - 히스토리 replay, returns/지표 계산은 기존대로 Runner/SDK/`ValidationPipeline`이 담당한다.
  - WS는 **이미 계산된 metrics/PnL·지표를 받아 정책을 적용하고, 결과/스냅샷/상태를 관리**하는 역할에 집중한다.
- Core Loop 변경과 무관한 인프라 리팩터링(브로커 교체, DAG 모델 재설계 등)은 이 로드맵 범위에서 다루지 않는다.

---

## Phase 0 — 목표 형상·계약 정리 (문서 중심)

**목표:** 구현에 앞서 “어디로 가는지”에 대한 서술을 명확히 하고, 기존 문서와 충돌이 없도록 한다.

### 해야 할 일

- `architecture/architecture.md`·`world/world.md`·`design/worldservice_evaluation_runs_and_metrics_api.md`를 기준으로 다음을 문장으로 고정한다.
  - **WS SSOT 원칙:** 실행 모드/단계의 단일 진실 소스는 항상 WorldService의 `effective_mode`/정책 결과다.
  - Runner/SDK는 `mode`를 선택하더라도, **WS 결정이 존재하는 한 항상 이를 우선한다.**
  - “모드는 선택값, WS `effective_mode` + world 정책은 계약”이라는 관점을 문서에서 일관되게 강조한다.
- World 정책 DSL에서 이미 존재하는 필드들(`data_currency`, `selection.gates`, `hysteresis` 등)을  
  “Core Loop 단계별 결정에 사용되는 1급 개념”으로 명시한다.

### 산출물

- 업데이트된 설계 문서:
  - WS SSOT·safe_mode·강등 규칙이 명확히 서술된 `architecture/architecture.md`/`world/world.md`
  - Evaluation Run 개념이 설명된 `design/worldservice_evaluation_runs_and_metrics_api.md`
- 이 로드맵 문서(`design/core_loop_world_roadmap.md`)를 **작업자용 참조**로 링크.

---

## Phase 1 — WS‑우선 모드 결정 계약 강화

**목표:** 현재 v2 구현이 이미 가진 “WS 결정 우선, 기본은 compute‑only(backtest)” 행동을 **계약 수준으로 못 박고, 코드·테스트에 반영**한다.

### 해야 할 일

1. **모드 결정 흐름 정리**
   - `qmtl.runtime.sdk.mode.Mode` / `mode_to_execution_domain` / `execution_domain_to_mode` / `effective_mode_to_mode` 사용처를 점검한다.
   - `qmtl.runtime.sdk.execution_context.resolve_execution_context`와  
     `qmtl.runtime.helpers.runtime.determine_execution_mode`가  
     아래 순서를 따르도록 확인·보완한다.
     1. explicit `mode` 인자
     2. 기존 `execution_mode` 컨텍스트
     3. WS `effective_mode`에서 온 domain 힌트
     4. 그 외에는 `backtest` (safe default)

2. **WS 결정 우선 적용**
   - Gateway/SDK가 WS `DecisionEnvelope` / `ActivationEnvelope`를 수신할 때:
     - `effective_mode`를 로컬 `compute_context` 및 `SubmitResult.ws.*`에 저장한다.
     - Runner/SDK가 자체적으로 execution_domain을 “승격”하지 않도록 보장한다.

3. **강등(safe_mode)·compute‑only 계약**
   - WS 결정이 없거나 stale일 때,  
     또는 `as_of`/`dataset_fingerprint`가 요구 조건을 만족하지 않을 때:
     - 항상 `execution_domain = backtest`, 주문 게이트 OFF, `safe_mode=True`, `downgraded=True`로 수렴하도록 한다.
   - 이 동작을 Core Loop 계약 테스트(`tests/e2e/core_loop`)와  
     별도 유닛 테스트에서 검증한다.

### 산출물

- 코드:
  - `runtime/sdk/execution_context.py`, `runtime/helpers/runtime.py`, `runtime/sdk/submit.py`의 모드·도메인 결정 경로가 WS‑우선 규칙을 따른다.
- 테스트:
  - WS 결정 부재/만료/에러 시 compute‑only로 강등되는 시나리오.
  - WS `effective_mode=validate/compute-only/paper/live`에 따라 SDK가 도메인을 어떻게 설정하는지 검증.

---

## Phase 2 — Evaluation Run을 1급 개념으로 올리기

**목표:** “이 제출이 지금 월드 내에서 어떤 단계인지”를 월드·WS 관점에서 추적할 수 있도록, Evaluation Run 모델을 실제 도입한다.

### 해야 할 일

1. **모델 정의**
   - `design/worldservice_evaluation_runs_and_metrics_api.md`의 정의를 기반으로,  
     WorldService 내부에 다음 스키마를 도입한다.
     - 키: `(world_id, strategy_id, evaluation_run_id)`
     - 상태: `submitted / backtest_running / evaluating / evaluated / activated / rejected / expired`
     - 메타: 생성/갱신 시간, 사용된 데이터 윈도우, 사용된 정책 버전 등.

2. **Runner.submit ↔ Evaluation Run 연동**
   - Runner.submit 호출 시:
     - WS/Gateway가 **평가 런을 생성**하거나 이미 존재하는 런을 갱신한다.
     - `SubmitResult`에 적어도 다음 중 하나를 포함한다.
       - `evaluation_run_id`
       - `evaluation_run_url` (상태/메트릭 조회용 링크)
     - (권장) 평가 런 산출물에 “검증/리스크 입력 스냅샷”을 참조로 남긴다.
       - 예: `risk_snapshot_version` 또는 `risk_snapshot_ref`(= `risk_signal_hub`의 `(world_id, version)` 혹은 URL)
   - 초기 단계에서는 여전히 “동기 파이프라인”으로 돌아도 괜찮지만,  
     **결과가 어디에 기록되는지**가 Evaluation Run으로 명확히 남아야 한다.

3. **상태 전이 구현**
   - Runner/SDK가 backtest/Validation/WS Evaluate를 수행하는 동안:
     - 적절한 시점에 `backtest_running` / `evaluating` / `evaluated` 등으로 상태를 업데이트한다.
   - `/worlds/{world}/strategies/{strategy}/runs/{run_id}` 형태의 상태 조회 API를 시범 구현한다.

### 산출물

- WS 코드:
  - Evaluation Run 저장소/모델 + 상태 전이 로직.
- API:
  - 평가 런 상태 조회 endpoint (초기에는 internal/admin 용도여도 괜찮다).
- Runner/SDK:
  - `SubmitResult`에 evaluation run 식별자를 포함.

---

## Phase 3 — world‑first 제출 UX & mode 인자 축소

**목표:** 실사용 DX를 “전략 + 월드” 중심으로 재정렬하고, `mode`는 점차 hint/고급 옵션으로 밀어낸다.

### 해야 할 일

1. **API 서피스 정리**
   - Python:
     - `Runner.submit(MyStrategy, world="...")`를 문서/예제에서 **기본 추천 경로**로 만든다.
     - `mode=` 인자는 여전히 허용하되, docstring/가이드에서 “advanced/실험용”으로 명시한다.
   - CLI:
     - `qmtl submit strategy.py --world my-world`를 권장 기본 형식으로 문서화한다.
     - `--mode` 플래그는 고급 옵션 섹션으로 이동한다.

2. **mode=None 코드 경로 지원**

   - 내부적으로 `mode=None`을 허용하고, 이 경우:
     - 실행 도메인 선택은 **WS `effective_mode` + world/data 정책**에 따라 결정된다.
     - Runner/SDK는 compute‑only 강등·게이트 설정만 담당한다.

3. **리그레이션 방지**

   - 기존 `mode=Mode.BACKTEST/PAPER/LIVE` 호출은 계속 동작하되,
     - WS가 붙어 있을 때는 `effective_mode`가 항상 최종 권위가 됨을 테스트로 보장한다.

### 산출물

- 문서:
  - Getting Started/Guides/Architecture 문서에서 “mode 없는 submit”을 기본 흐름으로 예시.
- 코드:
  - `mode=None` 경로 지원 및 테스트.

---

## Phase 4 — backtest/paper/live 캠페인 오케스트레이션

**목표:** World 정책과 Evaluation Run을 이용해 “backtest 캠페인 → paper 캠페인 → (선택적) live 캠페인”을 자동·반복적으로 관리할 수 있는 기반을 만든다.

여기서 `paper_campaign`은 운영 관점의 **dryrun(페이퍼 런)** 단계로, live 적용 전 “실전과 유사한 조건에서의 관찰/검증”을 위해 존재한다.

### 해야 할 일

1. **정책 DSL에 캠페인 윈도우 도입**
   - `world/world.md`의 정책 예시에 다음과 같은 필드를 추가·정의한다 (이름은 조정 가능).
     - `campaign.backtest.window`: 최소 backtest 관찰 기간 (예: `180d`)
     - `campaign.paper.window`: 최소 paper 관찰 기간
     - `campaign.common.min_trades_per_window`, `min_sample_days` 등
   - 각 필드는 “해당 단계에서 최소로 관찰되어야 하는 PnL/지표 윈도우”로 설명한다.

2. **캠페인 상태 모델**

   - WorldService에서 Evaluation Run 집계 결과를 기반으로, 월드/전략 조합에 대해 다음과 같은 상태를 유지한다.
     - `phase: backtest_campaign | paper_campaign | live_campaign`
     - 각 phase에 대해:
       - 관찰 시작/종료 시점
       - 관찰된 sample_days, trades, sharpe, max_dd, drawdown episode 등 핵심 지표
       - “승격 가능/불가능” 플래그 및 이유

3. **스케줄링 전략**

   - 초기 단계에서는 **외부 스케줄러/워크플로**를 전제로 단순하게 시작한다.
     - 예: “매일 1회 `/worlds/{id}/evaluate` 호출 → 정책 기반 승격 후보 계산 → `/apply`로 반영 또는 큐에 보관”.
     - 권장: 외부 스케줄러가 “다음에 무엇을 호출해야 하는지”를 얻기 위해, WorldService가 상태를 읽고 **추천 액션을 반환하는 tick 엔드포인트**를 제공한다(사이드이펙트 없음).
       - 예: `POST /worlds/{id}/campaign/tick` → `evaluate(backtest/paper)` 또는 `promotions/live/auto-apply` 호출 권장 목록 반환
     - (옵션) 외부 엔진 없이도 qmtl 내부 실행기로 운영할 수 있다.
       - 예: `qmtl world campaign-execute <world> [--execute]`, `qmtl world campaign-loop <world> --interval-sec 3600 [--execute]`
   - 이후 필요 시 WorldService 내부에 간단한 주기 평가 루프를 추가할 수 있다.

4. **Runner/CLI와의 연결**

   - Runner.submit은 여전히 “단일 호출”이지만,  
     - `SubmitResult` 또는 별도 CLI 명령어에서 “현재 캠페인 phase/윈도우/승격 조건”을 조회할 수 있게 한다.

### 산출물

- 정책:
  - 캠페인 윈도우·조건이 들어간 world policy 예제.
- WS:
  - 캠페인 상태 집계·조회 API (phase, 진행률, 승격 가능 여부).
- CLI:
  - `qmtl world status` 등에서 캠페인 phase와 핵심 지표를 요약해서 보여주는 명령.

권장 최소 API/CLI (예시):
- `GET /worlds/{world}/campaign/status[?strategy_id=...]` (phase, 진행률, 승격 가능 여부/사유)
- `qmtl world status <world> --strategy <sid>` (캠페인 phase/승격 가능 여부 요약 포함)

---

## Phase 5 — 검증 단계 고도화 & live 승격 거버넌스

**목표:** 소규모 조직에서도 “기술로 리스크를 통제”할 수 있을 만큼 강한 검증 단계를 만들고, live 승격은 기본적으로 운영/거버넌스 단계에 남겨 둔다.

### 선행조건 (Risk Signal Hub 입력 SSOT)

Phase 5의 “강한 검증/리스크 컷/스트레스”는 입력 데이터가 흔들리면 곧바로 불안정해진다. 따라서 아래 조건을 Phase 5 착수(또는 최소한 Phase 5의 blocking 룰 도입) 전제 조건으로 둔다.

- **프로듀서 커버리지 최소 기준**: 월드의 핵심 실행 경로(최소 rebalancing/activation, 가능하면 live 모니터링 경로)가 `risk_signal_hub`에 스냅샷을 지속적으로 적재한다.
- **신선도/결측 가시화**: `risk_hub_snapshot_lag_seconds`, `risk_hub_snapshot_missing_total` 지표로 stale/missing이 관측 가능하고, 알람/런북 경로가 준비되어 있다.
- **스테이지 라벨 안정화**: 스냅샷은 `X-Stage`/`provenance.stage`를 통해 stage 라벨이 항상 존재하며(backtest/paper/live 등), dedupe/알람이 `unknown`에 과도하게 몰리지 않는다.
- **fail-closed 합의**: 스냅샷이 missing/expired일 때 Phase 5 검증은 “보수적 강등(주문 게이트/승격 차단)”으로 수렴한다.

관련: [Risk Signal Hub 아키텍처](../architecture/risk_signal_hub.md), [운영 런북](../operations/risk_signal_hub_runbook.md)

### 해야 할 일

1. **월드 검증 단계 고도화**

   - World 정책 DSL에서 **검증 전용 필드**를 명시적으로 구분한다.
     - 예: `validation:` 블록 아래에
       - 데이터 통화성(데이터 랙, missing coverage 비율)
       - 샘플 충분성(`sample_days`, `trades_60d`, `notional_turnover`)
       - 리스크 컷(`max_dd_Xd`, `ulcer_index`, tail risk proxy)
       - 시나리오/스트레스 테스트 결과 플래그
   - 이 블록은 “**live 후보군에 오르기 위한 최소 조건**”을 정의하는 곳으로 문서화한다.
   - (정렬) 검증/스트레스/실현 리턴 등 “입력 스냅샷 SSOT”는 `risk_signal_hub`를 기준으로 읽는다.
     - WS/Exit Engine/모니터링이 동일한 `version/hash/as_of` 스냅샷을 공유하도록 설계한다.
     - 관련: [Risk Signal Hub 아키텍처](../architecture/risk_signal_hub.md)

2. **live 승격 거버넌스 정책 (월드별)**

   - World 정책 DSL에 `governance.live_promotion` 블록을 도입해, 월드마다 live 승격 방식을 고정한다.
   - 중요한 불변조건: `governance.live_promotion`는 **“live 전환을 어떻게 실행할지”**만 결정한다.  
     즉 `auto_apply`로 설정하더라도, Phase 4의 `paper_campaign`(= dryrun)과 Phase 5의 `validation` 게이트는 **생략되지 않는다**.
   - 최소 스키마(예시):

     ```yaml
     governance:
       live_promotion:
         mode: manual_approval  # disabled | manual_approval | auto_apply
     ```

   - `mode`의 의미(WS 관점):
     - `disabled`: live 승격을 **절대 수행하지 않는다**. (후보 선정/리포트는 가능)
     - `manual_approval` (기본값): backtest/paper 캠페인(dryrun)과 `validation`을 통과한 전략에 대해, WS는 `pending_live_approval` 상태를 남긴다. 운영자가 `/apply` 또는 승인 API/CLI로 명시적으로 승인해야 live 적용이 일어난다.
     - `auto_apply`: backtest/paper 캠페인(dryrun)과 `validation`을 통과한 전략에 대해, WS가 승격 조건을 만족하면 **자동으로 apply**한다. 단, 아래 fail‑closed 조건 및 가드레일을 만족하지 못하면 자동 승격은 차단되어야 한다.

   - 승인/감사(Audit) 요구사항(권장):
     - `manual_approval` 모드에서는 “누가/언제/무엇을/왜”가 남도록 승인 레코드를 1급으로 둔다.
       - 예: `approval_request_id`, `requested_at`, `approved_at`, `approved_by`, `comment`, `decision_reason`
     - `auto_apply` 모드에서도 동일한 수준의 적용 로그(자동 결정 사유 포함)가 남아야 한다.

   - 가드레일(권장, 이름은 조정 가능):
     - `cooldown`: 최근 승격 이후 재승격 최소 대기 시간
     - `max_live_slots`: 동시에 live로 올릴 수 있는 전략 수 상한
     - `canary_fraction`: 자동 승격을 “전체”가 아니라 일부에만 적용하는 비율/슬롯
     - `approvers`: 승인 가능한 주체(역할/계정) 목록

   - fail‑closed 규칙(필수):
     - `risk_signal_hub` 스냅샷이 missing/expired/stale이거나, `as_of`/`dataset_fingerprint`가 요구 조건을 만족하지 못하면
       - 승격은 `disabled`처럼 **항상 차단**하고, 후보/리포트에는 차단 사유를 노출한다.

   - CLI/툴 연계(필수):
     - 운영자가 “현재 상태를 보고 → 승인을 남기고(옵션) → apply를 실행”할 수 있어야 한다.
	     - 최소 CLI 서피스(예시, 이름은 조정 가능):
	       - 상태 조회:
	         - `qmtl world status <world> [--strategy <sid>]`  
	           (캠페인 phase, 최근 evaluation run, `validation` 통과 여부, `governance.live_promotion.mode`, `pending_live_approval` 여부/사유 요약)
	         - `qmtl world run-status <world> --strategy <sid> --run <id|latest>`  
	           (상태/메트릭/스냅샷 링크; 관련 설계: `design/worldservice_evaluation_runs_and_metrics_api.md`)
	       - 승인/거부(= `manual_approval` 모드에서만 활성):
	         - `qmtl world live-approve <world> --strategy <sid> --run <run_id> --comment ...`
	         - `qmtl world live-reject <world> --strategy <sid> --run <run_id> --comment ...`
	       - 적용:
	         - `qmtl world apply <world> --run-id <uuid> --plan-file <plan.json>` (기존)
	         - (권장) `qmtl world live-apply <world> --strategy <sid> --run <run_id> --run-id <uuid>`  
	           (WS가 계산한 “승격 플랜”을 조회→검증→2‑phase apply로 위임)
     - `auto_apply` 모드에서도, 위 명령은 “현재 상태/최근 자동 적용 내역(감사 로그)”을 조회하는 읽기 전용 기능으로 유용하다.

	   - API 연계(필수):
	     - 조회:
	       - `GET /worlds/{world}/strategies/{strategy}/runs/{run}` (상태)
	       - `GET /worlds/{world}/strategies/{strategy}/runs/{run}/metrics` (평가/검증 결과)
	       - `GET /worlds/{world}/decide` + `GET /worlds/{world}/activation` (현재 effective_mode/activation 스냅샷)
	     - 승인(수동 승인 모드):
	       - `POST /worlds/{world}/promotions/live/approve` (idempotent; actor/reason/timestamp 포함)
	       - `POST /worlds/{world}/promotions/live/reject` (idempotent; actor/reason/timestamp 포함)
	     - 적용:
	       - 최종 적용은 `POST /worlds/{id}/apply` (2‑phase apply)로 수렴시키되,
	         “evaluation run → activation plan” 변환 결과(= promote/demote, activate/deactivate)가
	         CLI/운영자가 검토 가능한 형태로 제공되어야 한다(예: `GET /worlds/{world}/promotions/live/plan?strategy_id=...&run_id=...`).
	         - 권장: 위 plan 응답에는 `pending_manual_approval`(수동 승인 대기)과 `blocked_reasons`(차단 사유 코드 목록), `eligible`(현재 정책/가드레일 기준으로 승격 가능 여부) 같은 필드를 포함해,
	           운영자가 “왜 아직 승격이 안 되는지(= dryrun/validation/스냅샷/fail‑closed/쿨다운 등)”를 빠르게 판단할 수 있어야 한다.
	       - `governance.live_promotion.mode=auto_apply`의 초기 구현은 “외부 스케줄러가 호출하는 자동 적용 엔드포인트”로 시작할 수 있다.
	         - 예: `POST /worlds/{world}/promotions/live/auto-apply`
	       - 후보군 조회(권장):
	         - `GET /worlds/{world}/promotions/live/candidates` (최신 paper run 기준 후보군 요약)
	         - (권장 CLI) `qmtl world live-candidates <world> [--include-plan]`
	     - RBAC:
	       - 승인/적용은 operator‑only(또는 별도 role)로 제한하고, 모든 호출은 감사 로그로 남긴다.

3. **운영자 친화적 리포트**

   - Evaluation Run / 캠페인 상태 / 검증 결과를 바탕으로, 운영자·리스크 담당자가 이해하기 쉬운 리포트를 설계한다.
     - 예: “최근 180일 Sharpe ≥ 0.8, max_dd ≤ 20%, 거래일 ≥ 60일을 충족하여 live 후보입니다.  
       다만 상관/섹터 제약 관점에서 A/B 전략과 다소 중복이 있으니 확인이 필요합니다.”
   - CLI/웹 UI/로그 링크 등 어떤 채널에서 이 정보를 볼지까지 포함해 설계한다.

### 산출물

- 정책:
  - 검증 단계 고도화가 반영된 world policy 예시 (`validation` 블록, 검증 지표·임계값).
- WS/도구:
  - live 승격 후보군 목록, 승격 사유/거부 사유를 요약하는 API/CLI/리포트.

---

## 6. 이 문서를 사용하는 방법 (작업자용 TL;DR)

1. **지금 내가 만지는 코드가 어느 Phase에 속하는지 먼저 정한다.**
   - 모드 결정/compute‑only 강등 로직을 건드린다면 → Phase 1.
   - Evaluation Run 모델/WS API를 바꾼다면 → Phase 2.
   - World 정책 DSL·캠페인 윈도우를 손본다면 → Phase 4–5.

2. **해당 Phase 섹션의 “해야 할 일/산출물” 체크리스트를 그대로 TODO로 사용한다.**
   - 새 기능을 추가할 때는 “이 로드맵의 어느 단계에 속하는지”를 PR/이슈 설명에 명시한다.

3. **Phase를 건너뛰지 않는다.**
   - 예를 들어 Evaluation Run을 제대로 도입하지 않은 상태에서 캠페인 오케스트레이션을 구현하면,
     - 디버깅이 어렵고, WS/Runner 간 책임 경계가 모호해지기 좋다.

4. **live 자동 승격은 항상 마지막에, 그리고 기본은 `manual_approval`.**
   - 이 문서는 **소규모 조직이 기술로 리스크를 제어할 수 있는 기반**을 제공하려는 것이지,
     - “사람 손을 완전히 떼는 live 자동화”를 지향하지 않는다.
   - live 자동 승격이 필요하더라도, 충분한 기간의 검증/캠페인·모니터링이 갖춰진 뒤,
     월드별 거버넌스 정책(`governance.live_promotion.mode=auto_apply`)로 제한된 환경에서만 opt‑in 하도록 계획한다.

이 로드맵 하나만으로도 “Core Loop를 월드 중심으로 고도화한다”는 목적과 방향성을 잃지 않고, 각 단계에서 해야 할 일을 판단할 수 있어야 한다. 세부 API·스키마는 관련 설계 문서(`architecture/*.md`, `world/*.md`, `design/worldservice_evaluation_runs_and_metrics_api.md`)를 함께 참고하되, **“지금 이 변경이 전체 그림에서 어느 Phase인지”**는 항상 이 문서를 기준으로 정한다.

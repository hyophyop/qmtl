---
title: "전략/노드 자동 증류 설계 스케치"
tags: [design, distillation, world, validation, governance]
author: "QMTL Team"
last_modified: 2025-12-30
status: draft
---

{{ nav_links() }}

# 전략/노드 자동 증류 설계 스케치

!!! warning "Icebox (참고용, 현재 작업 대상 아님)"
    이 문서는 `docs/ko/design/icebox/`에 보관된 참고용 설계 스케치입니다. **현재 작업 대상(SSOT)** 이 아니며, 필요 시 배경/아이디어 참고로만 사용하세요. 채택한 내용은 `docs/ko/architecture/` 또는 코드/테스트로 승격해 반영합니다.

## 0. 목표

QMTL에서 “전략/노드가 축적될수록, 사람이 보던 패턴과 운영 규칙이 점진적으로 자동화(증류)되는” 경로를 설계한다.

핵심은 **UI가 아니라 WorldService 정책/검증/거버넌스**에 있다:

- UI는 관측/승인 표면(consumer)이고,
- 증류의 SSOT는 `EvaluationRun` + `Evaluation Store` + WorldPolicy(DSL)이며,
- 어떤 경우에도 “추천(recommendation)”은 “결정(decision)”을 대체하지 않는다(승인/감사/롤백 가능).

관련 문서:

- World 스펙: [world/world.md](../../world/world.md)
- Core Loop × WorldService(승격 거버넌스): [architecture/core_loop_world_automation.md](../../architecture/core_loop_world_automation.md)
- World 검증 계층(icebox): [world_validation_architecture.md](world_validation_architecture.md)
- MRM 프레임워크(icebox): [model_risk_management_framework.md](model_risk_management_framework.md)
- Evaluation Store 운영: [operations/evaluation_store.md](../../operations/evaluation_store.md)
- 결정성 런북(run_manifest/NodeID/TagQuery): [operations/determinism.md](../../operations/determinism.md)
- UI(icebox, 관측 표면): [qmtl_ui.md](qmtl_ui.md)

---

## 1. 범위와 비범위

### 1.1 범위

- 전략/노드 증류의 **개념 모델**(facts/decisions/recommendations)
- 증류 결과가 World 정책/검증/거버넌스에 **어떻게 연결되는지**
- 최소 구현(v0→v1)으로 갈 수 있는 **데이터 모델/인터페이스 스케치**

### 1.2 비범위

- 특정 전략 아이디어의 알파 타당성 논증(전략 레포/KB 영역)
- 특정 수학적 방법(PBO/CSCV/DSR/부트스트랩)의 완전한 구현 상세
- 신규 대규모 인프라 도입(새 메시지 브로커/새 DB 강제 등)

---

## 2. 핵심 원칙(월가식 업그레이드 방향의 “고정점”)

증류는 “알파를 더 뽑는 자동화”가 아니라, **실패 모드와 운영 규칙을 제품화**하는 방향이어야 한다.

1. **무결성(Integrity) 선행**
   - 회계/리포팅 불일치가 있으면(예: daily 합 ≠ trades 합) 그 구간의 증류/승격 판단은 “금지/보류”가 기본값이다.
2. **실행 현실성(Execution realism) 고정**
   - 비용/슬리피지/체결 가정은 run마다 봉인되고(run_manifest), “좋은 성과”가 아니라 “보수적 가정에서도 살아남는지”가 후보의 기본 속성이다.
3. **과적합 통제는 ‘감각’이 아니라 ‘측정’**
   - DSR/PSR, (선택) CSCV 기반 PBO, 부트스트랩 성공확률 등은 증류 점수의 일부가 아니라 **게이트**(pass/fail/warn)로 먼저 취급한다.
4. **알파·리스크·실행 분리**
   - 재사용/표준화의 단위는 “전략 전체”보다 “노드/게이트/리스크 셸”이 우선이다.
5. **fail-closed + 감사 가능(append-only)**
   - 추천이 없어도 시스템은 보수적으로 동작해야 하고, 추천/승인/적용/롤백은 모두 `Evaluation Store`/감사 로그로 추적 가능해야 한다.

---

## 3. 개념 모델: Facts / Decisions / Recommendations

증류를 안정적으로 “축적 가능한 지식”으로 만들려면, 아래 세 층을 절대 섞지 않는다.

### 3.1 Facts (관측 사실, 불변 입력)

- `EvaluationRun` + `EvaluationMetrics` (returns/sample/risk/robustness/diagnostics)
- run 재현 입력(run_manifest):
  - 데이터 스냅샷/프리셋, 코드/노드 버전, 비용/슬리피지/체결 프로파일, 시드/반올림 규칙 등
- 실행/운영 사실:
  - risk_signal_hub 스냅샷(ref/inline), fill/position 이벤트, 비용 집계, override 이벤트, ex-post failures

Facts는 “다시 계산/재생성 가능해야 하며”, 수정은 새 revision으로만(append-only) 허용된다.

### 3.2 Decisions (정책/승인/적용 결과, SSOT)

- WorldPolicy(DSL)와 그 버전
- activation/allocation 적용 결과(2-phase apply) 및 실패/롤백 기록
- override 승인/재검토 결과(기한/사유 포함)

### 3.3 Recommendations (증류 결과, 제안)

증류 엔진이 생성하는 “사람/정책이 소비할 수 있는 제안”:

- 전략 단위:
  - `promote_candidate`, `demote_candidate`, `needs_review`, `paper_only_recommended` 등
- 노드/게이트 단위:
  - `bless_node_template`, `recommend_risk_shell`, `recommend_metric_gate`, `flag_data_leak_risk` 등

추천은 언제나:
- **근거(evidence)** 를 포함하고(어떤 Facts를 근거로 했는지),
- **권한 경계** 밖에서는 아무 것도 자동 적용하지 않으며,
- 승인/반려/보류가 가능한 상태 머신을 가진다.

---

## 4. 데이터 모델(스케치)

증류 결과를 “지식”으로 누적하려면, 단순 로그가 아니라 조회/비교 가능한 모델이 필요하다.

권장: Evaluation Store와 동일하게 **append-only revision** 모델로 저장한다.

```text
DistillationRun
  - distillation_run_id
  - world_id
  - as_of (UTC)
  - input_window (start/end)
  - distiller_version
  - inputs_ref (optional, offload)
  - created_at

DistillationRecommendation (append-only, revisioned)
  - world_id
  - subject_type: strategy|node_template|risk_shell|metric_gate
  - subject_id: strategy_id|node_template_id|...
  - action: bless|promote|demote|add_gate|tighten_gate|defer|investigate
  - status: proposed|approved|rejected|applied|superseded
  - score: float (optional)
  - confidence: low|medium|high
  - evidence:
      - evaluation_run_ids[]
      - key_metrics_snapshot
      - invariants_passed: bool
      - overfit_controls: {dsr, pbo, bootstrap_probs, ...}
      - execution_profile: {fee_model, slippage_model, stress_grid, ...}
      - notes
  - governance:
      - actor (on approve/reject)
      - reason
      - timestamp
  - created_at
```

---

## 5. 증류 파이프라인(스케치)

증류는 “점수 모델” 하나로 끝내기보다, **게이트 → 랭킹 → 제안** 순으로 분해하는 것이 안전하다.

### 5.1 Step 0 — 입력 윈도우와 후보군 정의

- world별로:
  - 관찰 윈도우(예: 최근 90일 backtest + 최근 30일 paper)를 고정
  - cohort/campaign(탐색 강도) 단위로 묶어 “같은 실험”의 변형들을 그룹화

### 5.2 Step 1 — 무결성 게이트(최우선)

- 회계/집계 인바리언트 위반이 있으면:
  - 해당 run은 “증류 입력에서 제외”
  - 전략/노드에 `flag_integrity_issue` 추천을 생성(원인 triage로 연결)

### 5.3 Step 2 — 실행 현실성 게이트(보수적 가정 스트레스)

- fee/slippage/funding 프로파일을 고정한 상태에서:
  - 스트레스 그리드(+bps, spread widening 등)에 대한 민감도를 측정
- “per-trade edge가 작은데 trade가 과다” 같은 패턴은 기본적으로 후보 점수를 깎는 것이 아니라,
  - “paper-forward 필요” 또는 “maker 전용/체결 모델 보수화 필요” 같은 **실행 추천**으로 분리한다.

### 5.4 Step 3 — 과적합 통제 게이트(승격 이전 필수)

- DSR/PSR, (선택) PBO/CSCV, 부트스트랩 성공확률을 기반으로:
  - `blocking/warn/info`로 상태를 만든다.
- 이 결과는 WorldPolicy의 validation gate와 정렬되어야 하며,
  - “추천 점수”에 섞지 말고 **정책/룰 결과로 남긴다**.

### 5.5 Step 4 — 안정성/기여도 추정(노드/게이트 레벨)

자동 증류의 핵심은 “전략 전체”보다 아래 단위의 재사용 후보를 뽑는 것이다.

- **노드/피처 기여도(예: ablation uplift)**
  - 동일 전략에서 특정 노드/게이트를 on/off 했을 때의 성능 차이를 기록
  - cohort 수준으로 누적해 “특정 레짐/시장에만 유효”도 함께 표시
- **리스크 셸 효과**
  - 알파는 유지하고 리스크 예산/킬스위치만 바꾼 단일 축 실험 결과를 누적해,
    “HV에서 파산을 제거한 조합”을 템플릿화 후보로 올린다.

### 5.6 Step 5 — 추천 생성 및 거버넌스 큐에 적재

- 추천은 항상 “왜 지금 필요한지”를 사람이 읽을 수 있게 남긴다:
  - 깨진 인바리언트, 레짐 붕괴 감지, 슬리피지 민감도, 과적합 지표 등
- 승인/반려/보류와 그 사유는 MRM/운영 프로세스에 편입한다.

---

## 6. 통합 지점(SSOT 경로에만 연결)

```mermaid
flowchart TD
  Facts[EvaluationRun & Metrics\n(run_manifest locked)] --> Store[(Evaluation Store)]
  Store --> Distiller[Distiller\n(batch or worker)]
  Distiller --> Reco[Recommendations\n(append-only)]
  Reco --> Gov[Governance\n(approve/reject/override)]
  Gov --> Policy[WorldPolicy changes\n+ Apply plan]
  Policy --> WS[WorldService decision/activation]
  UI[UI/Report] --> Store
  UI --> Reco
```

- Distiller는 WorldService 내부 워커이거나, 동일 스키마를 쓰는 배치 스크립트로 시작할 수 있다.
- 적용은 항상:
  - (A) WorldPolicy 버전 변경, 또는
  - (B) activation/allocation apply
  로만 일어난다(“추천이 곧 적용” 금지).

---

## 7. 단계적 도입(v0 → v1)

### v0 (빠른 시작)

- 배치 스크립트가:
  - 최근 EvaluationRun을 읽고,
  - 추천(마크다운/JSON)을 생성해 아티팩트로 남긴다.
- 운영은 사람이 읽고, 필요하면 WorldPolicy를 수동 변경한다.

### v1 (제품화)

- 추천을 Evaluation Store에 저장하고,
  - 승인/반려/적용 상태와 사유를 append-only로 남긴다.
- CI/운영 게이트:
  - 무결성 인바리언트 위반 시 “승격 후보 생성 금지”
  - 정책 변경 영향(policy diff) 리포트는 기존 Independent Validation 흐름을 따른다.

---

## 8. 전략 작성자 관점: 증류 가능(“distillable”) 최소 계약 (초안)

전략 구현은 DAG로 자유롭게 할 수 있지만, 자동 증류가 “누적 학습”처럼 동작하려면 **최소한의 표준 계약**이 필요하다.  
이 계약은 “전략이 원천 데이터를 직접 제공한다”는 의미가 아니라, **World/Runner가 재현 가능한 입력과 표준 출력 경계를 고정**한다는 의미다.

!!! warning "사전 검토 필요 (우려 사항)"
    아래 §8–§10의 제안은 “증류를 가능하게 만드는 최소 계약”을 정의하려는 초안이며, **사전에 면밀한 검토 없이는 SSOT(architecture/operations/code)로 승격하거나 구현을 시작하지 않는다.**  
    특히 (1) 자산군별 데이터 preset/스냅샷/캘린더/수수료·펀딩 등 입력 계약, (2) ablation(DAG rewrite/stub) 규약은 실행 파이프라인·결정성(run_manifest)·데이터 오염 경계와 충돌 가능성이 크므로, 자산군/월드 tier별로 리뷰 후 단계적으로 도입한다.

### 8.1 “원천 데이터”의 최소 단위는 전략이 아니라 World preset이다

증류 관점에서 전략 작성자가 제공해야 하는 최소 원천 데이터는 “파일/테이블”이 아니라, 아래를 만족하는 **World preset 선언과 사용**이다.

- World는 `data.presets[]`로 데이터 플레인의 SSOT를 선언한다. (참고: [world/world.md](../../world/world.md) §6.2)
- 전략/실행은 `Runner.submit(..., world=..., data_preset=...)` 경로로 수렴한다. (참고: [guides/strategy_workflow.md](../../guides/strategy_workflow.md))
- `StreamInput`은 가능하면 preset 기반으로 `history_provider`가 자동 주입되도록 유지하고,
  임의의 커스텀 provider는 “실험/레거시” 경로로 분리한다.

즉, 전략이 “증류 가능”하려면 **(A) 어떤 원천 데이터가 들어왔는지(preset/dataset)** 와
**(B) 그 데이터가 어느 시점 스냅샷인지(as_of/fingerprint)** 가 run_manifest에 봉인되어야 한다.

### 8.2 “최종 매매 시그널”의 최소 계약: Intent-first 권장

노드 그래프의 내부(예: z-score 계산)는 자유지만, World/검증/증류가 일관되게 비교하려면
“전략이 무엇을 매매하려 했는지”의 **표준 출력 경계**가 필요하다.

권장 기본값:

- 주문을 직접 생성하기보다, **포지션 타깃(의도, Intent)** 을 방출한다.
- 구현은 `PositionTargetNode` 및 `make_intent_first_nodeset` 레시피를 기본 경로로 둔다.

참고:

- 의도 기반 타깃 API: [reference/intent.md](../../reference/intent.md)

증류/검증은 최소한 다음을 식별할 수 있어야 한다.

- (1) “알파/시그널” 노드(예: z-score/alpha score)
- (2) “의도/타깃” 노드(포지션 타깃; 실행 파이프라인의 입력)

이 식별은 NodeID만으로는 부족할 수 있으므로, §8.4의 메타데이터(semantic tags)가 필요하다.

### 8.3 작성 중 힌트를 주는 방법(제안): Distillation Readiness Check

전략 작성 중 “내 DAG가 자동 증류에 필요한 최소 계약을 만족하는지”는 UI보다 **CLI/SDK 프리플라이트**로 제공하는 것이 효율적이다.

제안하는 표면(예시):

- `qmtl submit --lint distillation` (제출 전 체크)
- `qmtl tools sdk doctor --distillation` (DAG/노드셋 진단)
- `Runner.submit(..., strict_distillation=True)` (dev world에서 경고를 fail로 승격)

체크 항목(초안):

- World/preset: `world` 및 `data_preset`이 지정되었고, preset이 world에 존재하는지
- 입력 결정성: `dataset_fingerprint`/`as_of`/interval 정합성이 확보되어 default-safe 강등을 유발하지 않는지
- 출력 경계: Intent-first(타깃) 노드가 존재하거나, 최소한 “타깃/의도” 경계가 명시되어 있는지
- 실행 가정: fee/slippage(및 가능 시 funding) 프로파일이 run_manifest에 봉인되었는지
- 금지 패턴(예): extra bar feed/멀티 업스트림 오염 위험이 있는 경로가 없는지(또는 “non-distillable”로 라벨링되는지)

출력은 “왜 증류가 불가능한지”와 “빠른 수정(quick-fix)”를 함께 포함한다
(예: `alpha_node`를 `PositionTargetNode`로 감싸기, world preset 추가 등).

### 8.4 노드 증류를 위한 최소 메타데이터(초안)

노드 증류는 “어떤 노드가 어떤 역할인지”를 알아야 한다. 이를 코드 내부 규칙으로만 추론하면 불안정해지므로,
**가벼운 선언적 메타데이터**를 권장한다.

권장 최소(예시):

- `semantic_role`: `raw_input|feature|signal|intent|risk_shell|execution`
- `family`: 노드의 개념적 계열(예: `zscore`, `atr_gate`, `rsi_filter`)
- `ablation_group`: 함께 ablate해야 의미가 있는 묶음 키(예: `mr_leg`, `risk_shell_v1`)

우선은 기존 `StreamInput(tags=[...])`/TagQuery 메커니즘과 충돌하지 않도록 “태그 규약”으로 시작하고,
안정화되면 Node 스키마의 `metadata` 필드로 승격할 수 있다.

---

## 9. 노드 영향 측정을 위한 ablation: DAG가 깨지지 않게 하는 방법 (초안)

### 9.1 문제: “노드를 빼면 다음 노드가 깨진다”

전략에서 특정 노드의 영향을 보기 위해 노드를 제거하면, 그 노드를 입력으로 쓰는 downstream 노드가 즉시 깨진다.
특히 “한 노드 출력이 여러 downstream에서 조합”되는 DAG에서는 수동 ablation이 구조적으로 불안정하다.

따라서 ablation은 **전략 코드 편집이 아니라, 시스템이 DAG 변형을 생성하는 방식**으로 다뤄야 한다.

### 9.2 해결: DAG rewrite + schema-preserving stub

증류/검증 파이프라인은 “원본 DAG”와 “ablation DAG”를 별도로 생성해야 한다.

- 대상 노드를 삭제하지 않고,
- 동일한 출력 스키마를 유지하는 **stub 노드로 치환**한다.

stub의 동작은 최소 3가지 모드로 분리할 수 있다(예시):

- **constant baseline**: z-score=0 같은 “중립값”으로 고정
- **pass-through**: 특정 입력을 그대로 전달(의미가 있는 경우에 한함)
- **missing + fail-closed**: 값을 `NaN/null`로 만들고, downstream에서 “노출 축소/노트레이드”로 수렴하도록 게이트를 둔다

핵심은 “ablation이 DAG를 깨뜨리지 않고, 실행 경계에서 안전하게 fail-closed로 수렴”해야 한다는 점이다.

### 9.3 ablation 단위: node vs group vs subgraph

노드가 downstream에서 여러 번 재사용되는 경우, “단일 노드 ablation”은 모든 소비자에 동시에 영향을 준다.
이는 의도한 비교일 수도 있고(정상), 반대로 “부분만 끊어보고 싶다”는 요구로 이어질 수도 있다.

권장 우선순위:

1. **group/subgraph ablation**: `ablation_group` 단위로 의미 있는 묶음을 먼저 정의한다.
2. **node-level ablation**: leaf feature/게이트처럼 단독 효과가 명확한 노드에 제한한다.

### 9.4 기록: run_manifest / search_intensity 정렬

ablation은 “추가 실험”이므로, 아래가 함께 기록되어야 과적합 통제/감사 요구와 정렬된다.

- run_manifest에 `ablation_spec`(대상/모드/베이스라인 정의) 포함
- `search_intensity`(변형 수/실험 수)에 ablation 생성이 반영

---

## 10. 기존 설계와 상충 우려가 있는 개념들(초안)과 다루는 원칙

증류를 도입할 때 자주 충돌하는 개념들은 아래와 같고, 기본 원칙은 “SSOT 경로로만 연결 + fail-closed”다.

- **전략 코드(알파) vs 플랫폼(qmtl/) 경계**: 증류는 전략을 qmtl/로 옮기는 것이 아니라, 재사용 가능한 노드/템플릿 후보를 식별해 승격하는 방향으로만 다룬다.
- **결정성(NodeID/run_manifest) vs 빠른 실험**: ablation/변형은 DAG rewrite로 만들고, 결과는 별도 run_id/manifest로 봉인한다(원본 코드는 그대로 유지).
- **데이터 오염(멀티 스트림/extra feed)**: 오염 위험이 있는 경로는 “증류 입력 제외/라벨링”이 기본이며, 필요 시 world tier에서 fail로 승격한다.
- **정책 변경 거버넌스**: 추천이 정책 변경으로 이어질 때는 Independent Validation(policy diff)·override 재검토 규칙을 그대로 따른다.

---

## 11. “월가 수준” 성과 평가 자동화(초안): Stage-gate로 1차 의사결정까지

QMTL에서 “월가 수준”으로 구현 범위를 끌어올린다는 것은, 단순히 백테스트를 자동으로 돌리는 수준이 아니라:

1) 결과가 **회계적으로 맞는지**(무결성),  
2) 통계적으로 **과최적화가 아닌지**(견고성),  
3) 실행/리스크 가정이 **현실적인지**(실거래 가능성),  
4) 포트폴리오 내에서 **배치 가치가 있는지**(중복/상관/리스크 예산)  

를 **표준화된 파이프라인 + 정책(Stage-gate)** 으로 자동 판정하는 쪽에 가깝다.

### 11.1 자동화 가능한 상한선(현실적)

- **100% 자동화에 가깝다**: 무결성/재현성(회계 정합성, run_manifest 기반 재현, sanity check), 표준 KPI 측정/분해.
- **정량 판정까지 자동화 가능**: WF 기반 평가, DSR/PSR/PBO/부트스트랩 성공확률 산출 및 등급화(단, 컷라인은 정책으로 고정 필요).
- **80~90% 자동화 가능**: 실패 모드 트리아지(플레이북 태깅) + 표준 리포트 생성/보관/랭킹.
- **최종 배치 승인**은 보통 남긴다: 경제적 직관/용량/운영 리스크/규정 등 “정량화가 어려운 잔여 리스크”가 존재.

### 11.2 추천 Stage-gate 구조(초안)

아래는 “자동 평가/승격 추천”의 최소 골격이며, QMTL의 `EvaluationRun.summary.status/recommended_stage` 및 WorldPolicy `validation_profiles`와 정렬되어야 한다.

1. **Stage 0: Integrity Gate (PASS/FAIL)**
   - PnL 회계 정합성(예: `daily_*` 합 == `trades_*` 합), fee/friction 기록 0 여부, 결정론 재현성(동일 commit+dataset+manifest → 동일 해시).
2. **Stage 1: DEV 성과 + 비용 민감도**
   - net 성과가 friction에 의해 지배되는지(“friction dominates”), 표본 부족/0-trade 등 자동 분류 포함.
3. **Stage 2: WF 견고성**
   - OOS 합산, fold 부호 안정성, worst-fold, OOS/IS ratio 등 + 과적합 통제(DSR/PSR, 선택 PBO/CSCV, 부트스트랩 확률 KPI).
4. **Stage 3: Stress(슬리피지/수수료/레짐)**
   - 보수적 실행 가정 스트레스(+bps, spread widening) 및 레짐별 성과/취약성 평가.
5. **Stage 4: Paper-forward (실시간 시뮬레이션)**
   - 라이브 유사 조건에서 drift/실행 갭 검증(여기부터는 운영/관측 자동화가 핵심).
6. **Stage 5: Pilot (소액/저레버리지)**
   - 자동 모니터링 + kill switch + 리포팅 중심. “자동 자본 투입”은 일반적으로 two-key 승인으로 둔다.

### 11.3 Stage-gate 정책 템플릿(스케치)

아래는 “구조를 설명하기 위한” 스케치다. 실제 필드/DSL은 WorldPolicy/ValidationRule 구현과 동기화되어야 하며, 안정화 전에는 `diagnostics.extra_metrics` 기반의 additive 확장으로만 도입한다.

```yaml
# (sketch) config/worlds/<world_id>.yml
stage_gates:
  stage0_integrity:
    blocking:
      - invariants.pnlsums == true
      - invariants.fee_nonzero == true
      - determinism.repro_hash_match == true
  stage1_dev:
    blocking:
      - perf.net_sharpe >= 0.3
      - triage.friction_dominates == false
    watch:
      - triage.sample_starved == true
  stage2_wf:
    blocking:
      - wf.oos_sum_pnl > 0
      - robustness.dsr >= 0.15
    watch:
      - robustness.pbo > 0.2
  stage3_stress:
    blocking:
      - stress.slippage_bps_2.net_sharpe >= 0.0
    watch:
      - regime.fragile == true
  stage4_paper_forward:
    governance: manual_approval   # 승인/보류/반려
  stage5_pilot:
    governance: two_key
```

### 11.4 표준 리포트/아티팩트(필수 필드) 스케치

Stage-gate 자동화를 “운영 가능한 제품”으로 만들려면, 결과를 사람이 읽는 Markdown뿐 아니라 **기계가 읽는 JSON**으로도 고정해야 한다.

필수 아티팩트(예):

- `run_manifest.json` (입력 봉인)
- `evaluation_run.json` (WS SSOT)
- `evaluation_report.json` (표준 리포트; gates/triage 포함)
- `evaluation_report.md` (사람용 요약)

`evaluation_report.json` 최소 스키마(스케치):

```json
{
  "meta": {
    "world_id": "crypto_mom_1h",
    "strategy_id": "abcd",
    "run_id": "7a1b4c...",
    "stage": "backtest|paper|live",
    "commit_sha": "…",
    "data_preset": "ohlcv.binance.spot.1m",
    "dataset_fingerprint": "…",
    "as_of": "2025-12-30T00:00:00Z"
  },
  "integrity": {
    "status": "pass|fail",
    "invariants": {"pnl_sums_match": true, "fee_nonzero": true},
    "notes": []
  },
  "metrics": {
    "returns": {},
    "sample": {},
    "risk": {},
    "robustness": {},
    "diagnostics": {}
  },
  "stress": {"scenarios": []},
  "portfolio_fit": {"correlation": {}, "marginal_var_es": {}},
  "triage": {"tags": ["friction_dominates"], "reason": "…"},
  "stage_gate": {"stage": "stage2_wf", "status": "pass|watch|fail", "reasons": []}
}
```

---

{{ nav_links() }}

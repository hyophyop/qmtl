---
title: "WorldService — 월드 정책, 결정, 활성화"
tags: [architecture, world, policy]
author: "QMTL Team"
last_modified: 2025-11-12
---

{{ nav_links() }}

# WorldService — 월드 정책, 결정, 활성화

## 0. 역할과 범위

WorldService는 월드의 단일 진실 소스(SSOT)입니다. 다음을 소유합니다:
- 월드/정책 레지스트리: CRUD, 버저닝, 기본값, 롤백
- 결정 엔진: 데이터 신선도(data-currency), 표본 충분성, 게이트/점수/제약, 히스테리시스 → `effective_mode`(정책 문자열). Gateway는 결정/활성화 중계 시 이 모드에서 하위 `execution_domain`을 도출합니다.
- 활성화 제어: 전략/사이드별 가중치를 포함한 월드 단위 활성화 집합
- 일급 개념으로서의 ExecutionDomain: 월드별 `backtest | dryrun | live | shadow`
- 2‑단계 Apply: Freeze/Drain → Switch → Unfreeze, `run_id`로 멱등성 보장
- 감사 및 RBAC: 각 정책/업데이트/결정/적용 이벤트를 로깅하고 권한을 검사
- 이벤트: 내부 ControlBus로 활성화/정책 업데이트 발행

!!! warning "안전 기본값"
- 입력이 모호하거나 부족하면 live로 기본 설정하지 않고 compute-only(backtest)로 강등해야 합니다. `execution_domain`을 비우거나 생략한 WS API 호출이 live로 저장되면 안 됩니다.
- `allow_live=false`(기본)일 때는 운영자가 요청하더라도 활성/도메인이 live로 전환되지 않습니다. 정책 검증(필수 지표, 히스테리시스, dataset_fingerprint 고정)이 통과될 때에만 승격을 허용하세요.
- 클라이언트가 `execution_domain`을 생략하면 월드 노드·검증 캐시는 기본적으로 `backtest`로 저장됩니다. 의도한 도메인을 명시적으로 넣어야 live 범위로 잘못 저장되는 일을 막을 수 있습니다.

!!! note "설계 의도"
- WS는 `effective_mode`(정책 문자열)를 산출하고, Gateway는 이를 `execution_domain`으로 매핑해 공유 컴퓨트 컨텍스트로 전파합니다. SDK/Runner는 모드를 선택하지 않으며 입력으로만 취급합니다. 오래되었거나 알 수 없는 결정은 기본적으로 compute‑only(주문 게이트 OFF)로 처리합니다.
- 제출 메타의 `execution_domain` 값은 참조용 힌트일 뿐이며, 권한 있는 도메인 값은 WS가 산출한 `effective_mode`에서만 파생됩니다.

QMTL 전체의 핵심 가치인 **“전략 로직에만 집중하면 시스템이 알아서 최적화하고 수익을 낸다”**는 WorldService에서 다음과 같이 구체화됩니다.
- 전략 작성자는 전략을 월드에 제출하기만 하면 되고, **유효성 평가·승급/강등·가중치 조정·리스크 제약**은 WS 정책으로 자동 수행됩니다.
- 월드 수익률 관점에서는, `valid`로 판정된 전략만 포트폴리오에 편입되도록 하여 **월드 수준 위험 조정 수익이 악화되지 않도록** 설계합니다(단조 증가에 최대한 근접).
- SDK/Runner 및 Gateway는 WS가 제공하는 결정(envelope)의 소비자일 뿐이며, 사용자가 ExecutionDomain이나 Apply 프로토콜을 직접 제어하지 않아도 되도록 인터페이스를 구성합니다.
- 정책/스키마를 개편할 때는 하위 호환성을 위해 구/신 필드·모드를 장기간 병존시키지 않고, 명시적인 마이그레이션 기간 후에는 단일한 “신 정책 모델”만 유지하는 것을 원칙으로 합니다(단순성 > 하위 호환성).

비목표:
- 전략 인제스트, DAG diff, 큐/태그 디스커버리(각각 Gateway/DAG Manager 소유). 주문 I/O는 여기에서 다루지 않습니다.
- WorldService/Gateway 없이 Runner/SDK만으로 전체 전략 생애 주기와 최종 평가/게이팅을 처리하는 “순수 로컬 모드”를 정식 운영 모드로 지원하지 않습니다. SDK 레벨의 ValidationPipeline·PnL 헬퍼는 테스트/실험 용도이며, 정책·평가·게이팅의 SSOT는 항상 WorldService입니다.

### 0‑A. As‑Is / To‑Be 요약

#### 평가·활성화 플로우

- As‑Is
  - WS는 `/worlds/{id}/evaluate`에서 `EvaluateRequest(metrics, series, policy)`를 받아 정책 엔진(`Policy`)으로 **활성 집합(active[])**을 계산합니다.
  - SDK/Runner는 `ValidationPipeline`으로 로컬 평가를 먼저 수행한 뒤, 필요 시 WS 평가를 **보조 신호**로 조회합니다. 두 레이어가 모두 weight/contribution 개념을 가지고 있어, 어떤 값이 최종 기준인지 혼동 여지가 있습니다.
  - Activation 상태는 Redis/DB에 저장되고 ControlBus로 브로드캐스트되지만, Runner.submit / CLI와의 연결은 “활성화 결과를 어떻게 보여줄지” 수준에서 일부만 정리되어 있습니다.
- To‑Be
  - WS 평가 결과(active/weight/contribution/violations)가 **월드 차원의 단일 출처**로 간주되고, SDK/Runner는 이를 그대로 사용자에게 노출하되 `ValidationPipeline`은 힌트·로컬 사전 검사 역할로 한정됩니다.
  - `DecisionEnvelope`/`ActivationEnvelope` 스키마와 Runner/CLI `SubmitResult` 구조가 일치하도록 정리해, “전략 제출 → 월드 평가 결과 확인”이 한눈에 이어지도록 합니다.
- 계약 (정렬 상태)
  - `/worlds/{id}/evaluate` → `DecisionEnvelope`/`ActivationEnvelope` 값이 `SubmitResult.ws.decision/activation`에 그대로 매핑됩니다. CLI `--output json`은 WS/Precheck가 분리된 동일 JSON을 출력합니다.
  - 로컬 `ValidationPipeline` 출력은 `SubmitResult.precheck`에만 담기며, `status/weight/rank/contribution`의 SSOT는 WS입니다.
  - `ActivationEnvelope`(`GET/PUT /worlds/{id}/activation`) 필드와 `SubmitResult.ws.activation` 필드가 동일 스키마를 사용해 활성/weight/etag/run_id/state_hash를 노출합니다.

#### ExecutionDomain / effective_mode

- As‑Is
  - WS는 `effective_mode`(`validate | compute-only | paper | live`)를 계산하고, Gateway/SDK는 이를 `execution_domain(backtest/dryrun/live/shadow)`로 매핑합니다.
  - 일부 경로에서는 `meta.execution_domain` 힌트와 WS 결정이 동시에 존재하지만, 둘의 충돌/우선순위는 문서와 코드에 흩어져 있습니다.
- To‑Be
  - ExecutionDomain 결정 권한이 WS `effective_mode`에만 있다고 명시하고, Gateway/SDK는 항상 이 값을 기준으로만 도메인을 계산합니다.
  - `world/world.md`, `architecture.md`, `gateway.md`, 본 문서가 모두 같은 규범(매핑 테이블·우선순위)을 공유하도록 정리합니다.

#### 월드 자본 배분 / 리밸런싱

- As‑Is
  - `/allocations`, `/rebalancing/*`가 world/world‑간 자본 배분 플랜을 계산·기록할 수 있지만, Runner.submit/전략 제출 플로우와는 분리된 **운영자 주도 루프**로 사용됩니다.
  - Runner.submit/CLI는 제출된 world에 대해 `/allocations`의 최신 스냅샷(월드/전략 총합 비중)을 **조회·표시**하지만, 이는 적용 상태를 알려주는 표면일 뿐 자동 실행을 암시하지 않습니다. 자본 이동/실거래 반영은 여전히 운영자 플로우가 담당합니다.
  - Alpha metrics(`alpha_metrics`)를 rebalancing 플랜에 포함하는 v2 스키마가 도입되었으나, “전략 평가 → world allocation”을 한 문맥에서 설명하는 문서는 제한적입니다.
- To‑Be
  - 전략 제출/평가 루프와 world allocation 루프를 “표준 두 단계 루프”로 문서화하고, WS는 두 루프 모두의 SSOT 역할(평가/활성/배분)을 명확히 합니다.
  - Core Loop 표면(Runner.submit/CLI, 문서)이 `/allocations` 스냅샷과 연결되어, 평가/활성(제안) ↔ 자본 배분(적용) 단계를 명확히 구분한 채 탐색/인지를 쉽게 합니다. 적용·실행은 여전히 승인/감사 가능한 별도 플로우입니다.

---

## 1. 데이터 모델(규범)

Worlds (DB)
- world_id (pk, slug), name, description, owner, labels[]
- created_at, updated_at, state (ACTIVE|SUSPENDED|DELETED)
- default_policy_version, allow_live (bool), circuit_breaker (bool)

WorldPolicies (DB)
- (world_id, version) (pk), yaml (text), checksum, status (DRAFT|ACTIVE|DEPRECATED)
- created_by, created_at, valid_from (optional)

WorldActivation (Redis)
- Key: world:<id>:active → { strategy_id|side : { active, weight, etag, run_id, ts } }
- 스냅샷은 주기적으로 DB에 영속화되어 감사에 사용됩니다.

WorldAuditLog (DB)
- id, world_id, actor, event (create/update/apply/evaluate/activate/override)
- request, result, created_at, correlation_id

구현 메모: 레퍼런스 서비스는 지속형 백엔드(`qmtl.services.worldservice.storage.PersistentStorage`)
를 포함하며, 관계형 표면은 SQL(SQLite/Postgres)에, 활성화 상태는 Redis에 저장합니다.
프로덕션 배포는 기본적으로 이 백엔드를 사용하고, 단위 테스트는 여전히 인메모리 파사드를 활용할 수 있습니다.
아래 API는 이 내구성 어댑터를 대상으로 동작합니다.

### 1‑A. WVG 데이터 모델(규범)

WorldService는 World View Graph(WVG)의 SSOT입니다. 이는 전역 GSG 노드(Global Strategy Graph=GSG)를 참조하는 월드‑별 오버레이입니다:

- WorldNodeRef (DB): `(world_id, node_id, execution_domain)` → `status` (`unknown|validating|valid|invalid|running|paused|stopped|archived`), `last_eval_key`, `annotations{}`
- Validation (DB): `eval_key = blake3:(NodeID||WorldID||ContractID||DatasetFingerprint||CodeVersion||ResourcePolicy)` (**'blake3:' 접두사 필수**), `result`, `metrics{}`, `timestamp`
- DecisionsRequest (DB/API): `strategies`(정렬 및 중복 제거된 전략 식별자 리스트)를 `/worlds/{world_id}/decisions` 경로로 월드 단위 저장
- **EdgeOverride (DB, WVG scope):** 월드-로컬 도달성 제어 레코드. `(world_id, src_node_id, dst_node_id, active=false, reason)` 형태로 특정 월드에서 비활성화할 에지를 명시한다. 구현은 [`EdgeOverrideRepository`]({{ code_url('qmtl/services/worldservice/storage/edge_overrides.py#L13') }})와 WorldService [`/worlds/{world_id}/edges/overrides`]({{ code_url('qmtl/services/worldservice/routers/worlds.py#L109') }}) 라우트가 저장·노출한다.

SSOT 경계: WVG 객체는 DAG Manager가 저장하지 않습니다. WS가 수명주기를 소유하고 ControlBus로 변경을 발행합니다.

---

## 2. API 표면(요약)

CRUD
- POST /worlds | GET /worlds | GET /worlds/{id} | PUT /worlds/{id} | DELETE /worlds/{id}

정책(Policies)
- POST /worlds/{id}/policies  (upload new version)
- GET /worlds/{id}/policies   (list) | GET /worlds/{id}/policies/{v}
- POST /worlds/{id}/set-default?v=V

바인딩(Bindings)
- POST /worlds/{id}/bindings        (upsert WSB: bind `strategy_id` to world)
- GET  /worlds/{id}/bindings        (list; filter by `strategy_id`)

목적
- WSB는 각 제출마다 WVG에 `(world_id, strategy_id)` 루트가 존재하도록 보장합니다. 다중 월드를 대상으로 할 경우, 운영 격리와 자원 제어를 위해 월드별 별도 프로세스를 권장합니다.

결정 및 제어
- GET /worlds/{id}/decide?as_of=... → DecisionEnvelope
- POST /worlds/{id}/decisions       (replace world strategy set via DecisionsRequest)
- GET /worlds/{id}/activation?strategy_id=...&side=... → ActivationEnvelope
- PUT /worlds/{id}/activation          (manual override; optional TTL)
- POST /worlds/{id}/evaluate           (plan only)
- POST /worlds/{id}/apply              (2‑Phase apply; requires run_id)
- GET /worlds/{id}/audit               (paginated stream)

RBAC: 월드 범위 롤(owner, reader, operator). 민감 작업(`apply`, `activation PUT`)은 operator 권한이 필요합니다.

---

## 3. Envelopes (normative)

The canonical Pydantic models for these envelopes live in [`qmtl/services/worldservice/schemas.py`]({{ code_url('qmtl/services/worldservice/schemas.py') }}). ControlBus fan-out (e.g., `ActivationUpdated`) reuses these payloads; see [`docs/reference/schemas/event_activation_updated.schema.json`](../reference/schemas/event_activation_updated.schema.json) for the CloudEvent wrapper.

DecisionEnvelope
```json
{
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "effective_mode": "validate",  
  "reason": "data_currency_ok&gates_pass&hysteresis",
  "as_of": "2025-08-28T09:00:00Z",
  "ttl": "300s",
  "etag": "w:crypto_mom_1h:v3:1724835600"
}
```

`effective_mode` remains the policy string. Gateway/SDK derive an
ExecutionDomain from it and only attach `execution_domain` on the
ControlBus/WebSocket copies they relay downstream; the field is not part of
the canonical WorldService schema.

ActivationEnvelope
```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "effective_mode": "paper",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z",
  "phase": "unfreeze",
  "requires_ack": true,
  "sequence": 17
}
```

Field semantics and precedence
- `freeze=true` overrides `drain`; both imply orders gated OFF.
- `drain=true` blocks new orders but allows existing opens to complete naturally.
- When either `freeze` or `drain` is true, `active` is effectively false (explicit flags provided for clarity and auditability).
- `weight` soft‑scales sizing in the range [0.0, 1.0]. If absent, default is 1.0 when `active=true`, else 0.0.
- `effective_mode` communicates the policy string from WorldService (`validate|compute-only|paper|live`).
- Gateway derives an `execution_domain` when relaying the envelope downstream (ControlBus → SDK) by mapping `effective_mode` as `validate → backtest (orders gated OFF by default)`, `compute-only → backtest`, `paper/sim → dryrun`, `live → live`. `shadow` remains reserved for operator-led validation streams. The canonical ActivationEnvelope schema emitted by WorldService omits this derived field; Gateway adds it for clients so the mapping stays centralized.
- ControlBus 팬아웃 시 [`ActivationEventPublisher.update_activation_state`]({{ code_url('qmtl/services/worldservice/activation.py#L58') }})가 `phase`(`freeze|unfreeze`), `requires_ack`, `sequence`를 주입한다. `sequence`는 [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }})에서 run별 단조 증가 값으로 생성된다.
- `requires_ack=true`는 Gateway/SDK가 해당 `sequence`까지의 상태 변화를 수신하고 order gate를 계속 잠근 채 ACK를 반환해야 함을 뜻한다(SHALL). Freeze 단계 ACK가 도착하기 전에는 동일 run의 Unfreeze 이벤트를 적용하거나 주문 게이트를 열어서는 안 된다.

아이템포턴시(Idempotency): 컨슈머는 오래된 `etag`/`run_id` 이벤트를 무시해야 합니다(no‑op). 알 수 없거나 만료된 결정/활성화는 “비활성/안전” 상태로 간주합니다.

TTL 및 신선도(Staleness)
- DecisionEnvelope에는 TTL이 포함됩니다(미지정 시 기본 300초). TTL 경과 후 Gateway는 결정을 오래된 상태로 간주하고, 새 결정을 받을 때까지 안전 기본값인 compute‑only(주문 게이트 OFF)를 강제해야 합니다.
- Activation에는 TTL이 없지만 `etag`(선택적으로 `state_hash`)가 포함됩니다. 알 수 없거나 만료된 활성화 → 주문 게이트 OFF.

---

### 4. Execution Domains & Apply (normative)

- Domains: `backtest | dryrun | live | shadow`.
- Isolation invariants:
  - Cross‑domain edges MUST be disabled by default via `EdgeOverride` until a policy explicitly enables them post‑promotion.
  - Orders are always gated OFF while `freeze=true` during 2‑Phase apply.
  - Domain switch is atomic from the perspective of order gating: `Freeze/Drain → Switch(domain) → Unfreeze`.
  - ActivationUpdated ACK 수렴 절차:
    - Freeze/Drain 및 Unfreeze 단계 이벤트는 `requires_ack=true`, `phase`, `sequence` 메타데이터가 포함된 ControlBus 메시지로 게시된다.
    - Gateway는 `sequence` 기준으로 선형 재생을 보장하고, Freeze 이벤트에 대한 ACK가 도착하기 전에는 동일 run의 후속 이벤트(특히 Unfreeze)를 SDK로 전파하거나 주문 게이트를 해제해서는 안 된다(SHALL).
    - ACK는 ControlBus 또는 동일하게 구성된 응답 채널을 통해 보고되며, payload에는 `world_id`, `run_id`, 마지막으로 적용한 `sequence`와 같은 재동기화 정보를 포함해야 한다. run별로 단조 증가 값을 유지하고, 역순 ACK는 무시하거나 오류로 처리해야 한다(SHOULD).
- 2‑Phase Apply protocol (SHALL):
  1. **Freeze/Drain** — Activation entries set `active=false, freeze=true`; Gateway/SDK gate all order publications; EdgeOverride keeps live queues disconnected.
  2. **Switch** — ExecutionDomain updated (예: backtest→live), queue/topic bindings refreshed, Feature Artifact snapshot pinned via `dataset_fingerprint`.
  3. **Unfreeze** — Activation resumes (`freeze=false`) only after the new domain’s ActivationUpdated event is acknowledged by Gateway/SDK.
  - Single-flight guard: world 당 동시에 하나의 apply만 실행할 수 있다(SHALL). 중복 요청은 409를 반환하거나 큐에 보류한다.
  - Failure policy: Switch 단계에서 오류가 발생하면 즉시 직전 Activation snapshot으로 롤백하고 freeze 상태를 유지한다(SHALL).
  - Audit: WorldAuditLog에 `requested → freeze → switch → unfreeze → completed/rolled_back` 타임라인을 기록한다(SHOULD).
- Queue namespace guidance: 프로덕션에서는 `{world_id}.{execution_domain}.<topic>` 네임스페이스와 ACL을 사용해 교차 도메인 접근을 막는다(SHALL). NodeID/토픽 규범은 변하지 않는다.
- Dataset Fingerprint: Promotion은 특정 데이터 스냅샷(`dataset_fingerprint`)에 고정되어야 하며(SHALL), EvalKey에 포함돼 cross-domain 재검증을 분리한다.

---

## 4. 결정 의미론(Decision Semantics)

- 데이터 신선도(Data Currency): `now − data_end ≤ max_lag`이면 근실시간, 아니면 따라잡을 때까지 compute‑only 리플레이(주문 게이트 OFF 유지)
- 표본 충분성: 메트릭별 최소 일수/체결수/바 수 등을 기준으로 스코어링 전 게이트 적용
- 게이트/스코어/제약: 임계값 AND/OR, 가중 스코어, 상관/익스포저 제약
- 히스테리시스: `promote_after`, `demote_after`, `min_dwell`로 플래핑 방지

평가 결과는 DecisionEnvelope과(선택적으로) Apply 계획을 반환합니다.

### 4‑A. DecisionsRequest 업데이트(WVG)

- `/worlds/{world_id}/decisions`는 `DecisionsRequest`를 받아 해당 월드의 저장된 전략 목록을 원자적으로 교체합니다(MUST).
- 항목은 비어있지 않은 문자열인지 검증하고, 중복 제거 후 요청 순서를 보존해 영속화합니다(SHALL).
- 목록을 비우면 해당 월드의 모든 활성 전략이 제거되며, 이후 `/decide` 호출은 전략이 복원될 때까지 `validate` 모드를 반환합니다(SHOULD).

### 4‑B. EvalKey와 검증 캐싱

- EvalKey = `blake3(NodeID || WorldID || ExecutionDomain || ContractID || DatasetFingerprint || CodeVersion || ResourcePolicy)`
- ExecutionDomain은 해싱/저장 전 정규화(대소문자 무시)하여 도메인 스코프 캐시 키가 안정적으로 비교되도록 합니다.
- 구성 요소가 변경되면 캐시 무효화 및 재검증을 트리거합니다. 무효화는 스코프 도메인 엔트리를 제거하고(마지막 엔트리 제거 시 버킷 비움) 오래된 재사용을 방지합니다.

### 4‑C. 게이팅 정책 명세(규범)

정책 도구가 강제하는 참조 YAML 구조:

```yaml
gating_policy:
  promotion_point: "2025-10-01T00:00:00Z"
  apply: { mode: two_phase, freeze_timeout_ms: 30000 }
  domains: { from: backtest, to: live }
  clocks:
    backtest: { type: virtual, epoch0: "2020-01-01T00:00:00Z" }
    live:     { type: wall }
  dataset_fingerprint: "ohlcv:ASOF=2025-09-30T23:59:59Z"
  share_policy: "feature-artifacts-only"   # runtime cache sharing forbidden
  snapshot:
    strategy_plane: "cow"
    feature_plane: "readonly"
  risk_limits:
    max_pos_usd_long:  500000
    max_pos_usd_short: 500000
  divergence_guards:
    feature_drift_bp_long: 5
    feature_drift_bp_short: 5
    slippage_bp_long: 10
    slippage_bp_short: 12
  execution_model:
    fill: "bar-mid+slippage"
    fee_bp: 2
  can_short: true
  edges:
    pre_promotion:  { disable_edges_to: "live" }
    post_promotion: { enable_edges_to:  "live" }
  observability:
    slo: { cross_context_cache_hit: 0 }
    audit_topic: "gating.alerts"
```

- 정책은 반드시 `dataset_fingerprint`, 명시적 `share_policy`, 승격 전/후 엣지 오버라이드를 지정해야 합니다. 누락 시 Apply는 compute‑only로 강등되거나 거부됩니다.
- `observability.slo.cross_context_cache_hit`는 0이어야 하며(SHALL), 위반 시 실행이 차단됩니다. Gateway/SDK는 ControlBus 이벤트와 메트릭으로 이를 감시합니다.
- `snapshot`/`share_policy` 조합은 Feature Artifact Plane(§1.4) 규칙과 일치해야 합니다. Strategy Plane은 Copy‑on‑Write, Feature Plane은 읽기 전용 복제로만 공유합니다.
- `risk_limits`, `divergence_guards`, `execution_model`은 프로모션 전 검증에서 평가되며, 실패 시 Apply가 거부되고 freeze 상태가 유지됩니다.

!!! note "내부 정규 스키마와 프리셋의 관계"
    본 섹션의 `gating_policy` 구조는 WorldService 정책 엔진의 **내부 정규 스키마(SSOT)**를 정의합니다. Core Loop 단순화 및 정책 프리셋 도입은 사용자가 직접 작성해야 하는 월드/정책 설정 표면을 줄이기 위한 것이며, 이 스키마가 표현할 수 있는 게이팅·리스크·관측 정책의 **표현력을 축소하는 것을 목표로 하지 않습니다.**  
    프리셋/오버라이드·외부 정책 도구는 모두 이 정규 스키마로 컴파일되는 상위 인터페이스로 취급하며, 필요 시 고급/운영 플로우용 별도 진입점으로 이를 재노출할 수 있어야 합니다.

---

## 5. 할당 & 리밸런싱 API (규범)

WorldService는 월드 비중과 전략 슬리브를 조정하기 위한 두 가지 표면을 노출합니다. 모든 경로는 `mode='scaling'`(기본값)을 중심으로 동작하며, `overlay`는 구성값이 있을 때 지원되고 `hybrid`는 아직 미구현(HTTP 501)입니다.

### 5‑A. `POST /allocations` — 월드 비중 업서트

- **입력 스키마:** [`AllocationUpsertRequest`]({{ code_url('qmtl/services/worldservice/schemas.py#L278') }}). 필수 필드는 `run_id`, `total_equity`, `world_allocations{world_id→ratio}`, 현재 `positions[]`이며, 선택적으로 전략 총합(`strategy_alloc_*`)·최소 체결 노치(`min_trade_notional`)·심볼별 롯(`lot_size_by_symbol`)을 포함합니다.【F:qmtl/services/worldservice/schemas.py†L248-L314】
- **유효성 검사:** `world_allocations`는 비어 있을 수 없고 값은 [0,1] 범위여야 합니다. 범위를 벗어나면 422, 미지원 모드면 501을 반환합니다.【F:qmtl/services/worldservice/services.py†L184-L207】
- **Core Loop 노출:** Runner.submit/CLI는 제출된 world에 대해 `GET /allocations?world_id=...` 스냅샷을 조회해 **적용된 월드/전략 비중**을 표시합니다(조회 실패는 무시하며, 실행을 의미하지 않습니다).
- **run_id 멱등성:** 요청 본문(`run_id`/`execute`/`etag` 제외)을 해시해 `etag`를 생성합니다. 동일한 `run_id`로 상이한 페이로드를 보내면 409가 발생하고, 동일한 페이로드는 저장된 플랜과 실행 상태를 재사용합니다.【F:qmtl/services/worldservice/services.py†L129-L166】【F:qmtl/services/worldservice/services.py†L207-L236】
- **플랜 계산:** `MultiWorldProportionalRebalancer`가 월드/전략 수준 스케일링을 적용해 `per_world` 및 `global_deltas`를 산출합니다. 요청에 전략 합계가 없으면 현재 포지션 비중을 추론해 `scale-only` 모드로 동작합니다.【F:qmtl/services/worldservice/rebalancing/multi.py†L1-L111】【F:qmtl/services/worldservice/rebalancing/rule_based.py†L1-L74】
- **저장 & 이벤트:** 성공 시 `PersistentStorage`가 요청/플랜 스냅샷을 기록하고 최신 월드 비중/전략 비중을 영속화합니다. 이후 ControlBus에 `rebalancing_planned` 이벤트(월드별 `scale_world`, `scale_by_strategy`, `deltas`)를 발행해 Gateway가 재분배 작업을 브로드캐스트/측정할 수 있게 합니다.【F:qmtl/services/worldservice/services.py†L237-L311】【F:qmtl/services/worldservice/controlbus_producer.py†L96-L109】
- **외부 실행:** `execute=true`일 때 리밸런싱 실행기가 구성되어 있으면(`rebalance_executor`) 동기화된 `MultiWorldRebalanceRequest` 스냅샷으로 실행기를 호출하고 응답을 `execution_response`에 포함합니다. 실행기가 없으면 503, 실패하면 502를 반환하며, 성공 시 `executed=true`로 표시합니다.【F:qmtl/services/worldservice/services.py†L167-L318】
- **응답:** [`AllocationUpsertResponse`]({{ code_url('qmtl/services/worldservice/schemas.py#L295') }})는 계산된 플랜과 함께 `run_id`, `etag`, `executed`, (선택적) `execution_response`를 제공합니다.【F:qmtl/services/worldservice/services.py†L212-L235】【F:qmtl/services/worldservice/services.py†L312-L318】

### 5‑B. `POST /rebalancing/plan`

- 동일한 [`MultiWorldRebalanceRequest`]({{ code_url('qmtl/services/worldservice/schemas.py#L236') }})를 받아 `MultiWorldProportionalRebalancer`로 플랜을 산출합니다. `mode`가 `hybrid`면 501을 반환합니다. `overlay` 요청은 월드별 스케일·델타와 함께 `overlay_deltas` 및 다중 월드 합산 뷰(`global_deltas`)를 제공합니다.【F:qmtl/services/worldservice/routers/rebalancing.py†L21-L82】
- 이 엔드포인트는 상태를 저장하지 않고 감사 로그도 남기지 않습니다. 운영자는 플랜을 사전 검토하거나 시뮬레이션 파이프라인에서 사용합니다.

### 5‑C. `POST /rebalancing/apply`

- `/rebalancing/plan`과 동일한 계산을 수행한 뒤, 월드별 플랜과 전역 델타를 직렬화해 감사 스토리지에 기록합니다(베스트 에포트). ControlBus가 연결되어 있으면 월드별 `rebalancing_planned` 이벤트를 발행합니다.【F:qmtl/services/worldservice/routers/rebalancing.py†L84-L154】【F:qmtl/services/worldservice/storage/persistent.py†L850-L864】
- `/rebalancing/apply`는 월드 비중을 직접 변경하지 않습니다. `/allocations` 업서트 또는 외부 실행기가 실거래 계좌 업데이트를 담당하며, 이 엔드포인트는 “승인된 플랜”을 감사/모니터링 용도로 고정합니다.

### 5‑D. 스키마 버전 및 alpha 메트릭 핸드셰이크

- `/rebalancing/plan`과 `/rebalancing/apply`는 이제 `schema_version`을 협상하고, v2가 활성화되면 `alpha_metrics` 봉투를 플랜/글로벌 델타와 함께 반환합니다. WorldService는 `create_app()`과 `WorldServiceServerConfig`를 통해 `compat_rebalance_v2`/`alpha_metrics_required` 토글을 노출하며, 배포자는 이 플래그로 v2를 켜거나 필수로 만들 수 있습니다 (`api.py`와 `config.py`에서 설정 검사). v2가 비활성화되면 응답은 `schema_version=1`이고 메트릭을 생략하며, v2에서는 항상 `schema_version=2`와 `AlphaMetricsEnvelope`(per_world/per_strategy `alpha_performance` 사전 포함)를 반환하여 downstream 클라이언트가 안정적으로 파싱하도록 합니다. `alpha_metrics_required`가 켜지면 `schema_version<2` 요청은 계산 전에 거부되어 필수 메트릭을 기대하는 클라이언트가 조기에 실패할 수 있습니다.【F:qmtl/services/worldservice/api.py#L119-L210】【F:qmtl/services/worldservice/config.py#L25-L108】【F:qmtl/services/worldservice/routers/rebalancing.py#L54-L187】【F:qmtl/services/worldservice/schemas.py#L245-L308】
- 각 `alpha_metrics` 맵은 `alpha_performance.sharpe`, `alpha_performance.max_drawdown` 등의 키와 0.0 기본값을 사용하므로 파싱 로직은 추가 예외 없이 실행할 수 있습니다.【F:qmtl/services/worldservice/alpha_metrics.py#L1-L52】
- ControlBus `rebalancing_planned` 이벤트도 협상된 `schema_version`과 동일한 `alpha_metrics`를 포함시켜 Gateway ControlBus 소비자가 같은 `alpha_performance` 봉투를 WebSocket/CommitLog에 전파할 수 있습니다. (`docs/operations/rebalancing_schema_coordination.md`는 Gateway(#1512)와 SDK(#1511)가 v2를 함께 전환할 때 확인해야 할 체크리스트입니다).【F:qmtl/services/worldservice/controlbus_producer.py#L27-L52】【docs/operations/rebalancing_schema_coordination.md】

### 5‑E. ControlBus 연동 & 지표

- WorldService가 발행하는 `rebalancing_planned` 이벤트는 Gateway Consumer가 받아 WebSocket `rebalancing` 채널로 중계하고 다음 Prometheus 지표를 갱신합니다: `rebalance_plans_observed_total`, `rebalance_plan_last_delta_count`, `rebalance_plan_execution_attempts_total`, `rebalance_plan_execution_failures_total`. 이를 통해 운영자는 플랜 생성 빈도와 자동 실행 성공률을 추적할 수 있습니다.【F:qmtl/services/gateway/controlbus_consumer.py†L223-L276】【F:qmtl/services/gateway/metrics.py†L216-L592】

---

## 6. 보안 & RBAC

- 인증: 서비스 간 토큰(mTLS/JWT); 사용자 토큰은 Gateway에서 WS로 전달
- 권한: 월드 스코프 RBAC는 WS에서 강제; Gateway는 프록시 역할만 수행
- 감사: 모든 쓰기 작업과 평가에 correlation_id를 포함해 로깅

클록 규율(Clock Discipline)
- 결정은 시간에 의존합니다. WS는 단조 증가 서버 클록과 NTP 상태를 강제하며, 허용 가능한 클라이언트 스큐(예: ≤ 2초)를 문서화해야 합니다.

---

## 7. 관측(Observability) & SLO

메트릭 예시
- `world_decide_latency_ms_p95`, `world_apply_duration_ms_p95`
- `activation_skew_seconds`, `promotion_fail_total`, `demotion_fail_total`
- `registry_write_fail_total`, `audit_backlog_depth`
- `cross_context_cache_hit_total`(목표=0; 위반 시 프로모션 차단)

Skew 메트릭
- `activation_skew_seconds`는 이벤트 `ts`와 SDK 처리 시각의 차이를 월드별 p95로 집계합니다.

알림
- 결정 실패, 명시적 상태 폴링 실패, Gateway의 오래된 활성화 캐시
- `cross_context_cache_hit_total > 0`(치명): Apply 재개 전 도메인 혼합 조사

---

## 8. 장애 모드 & 복구

- WS 다운: Gateway는 캐시된 DecisionEnvelope이 신선할 경우 이를 반환, 아니면 안전 기본값(compute‑only/inactive). Activation은 기본 비활성.
- Redis 손실: 최신 스냅샷에서 Activation을 재구성; 일관성 회복 전까지 주문 게이트 유지.
- 정책 파싱 오류: 해당 버전 거부, 이전 기본값 유지.

---

## 9. 통합 & 이벤트

- Gateway: `/worlds/*` 프록시, TTL 기반 결정 캐시, `--allow-live` 가드 적용
- DAG Manager: 결정과는 독립, 큐/그래프 메타데이터만 연계
- ControlBus: WS는 ActivationUpdated/PolicyUpdated 발행; Gateway가 구독 후 WS를 통해 SDK로 중계

Runner & SDK 통합(명확화)
- SDK/Runner는 실행 모드를 노출하지 않습니다. 호출자는 전략 시작 시 `world_id`만 제공하며, Runner는 WorldService 결정과 활성화 이벤트를 따릅니다.
- DecisionEnvelope의 `effective_mode`는 WS가 계산하며 SDK는 입력으로 취급합니다. 알 수 없거나 오래된 결정은 compute‑only(주문 게이트 OFF)로 처리합니다.
- 제출 시 Gateway는 각 `world_id`에 대해 **WSB upsert**를 보장하며, WVG에 `WorldNodeRef(root)`를 생성/갱신한다.

---

## 10. Testing & Validation

- Contract tests for envelopes (Decision/Activation) using the JSON Schemas (reference/schemas.md).
- Idempotency tests: duplicate/out‑of‑order event handling based on `etag`/`run_id`.
- WS reconcile tests: initial snapshot vs. `state_hash` divergence handling and HTTP fallback.

{{ nav_links() }}

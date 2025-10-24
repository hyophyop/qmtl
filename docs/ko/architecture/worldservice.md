---
title: "WorldService — 월드 정책, 결정, 활성화"
tags: [architecture, world, policy]
author: "QMTL Team"
last_modified: 2025-09-22
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

!!! note "설계 의도"
- WS는 `effective_mode`(정책 문자열)를 산출하고, Gateway는 이를 `execution_domain`으로 매핑해 공유 컴퓨트 컨텍스트로 전파합니다. SDK/Runner는 모드를 선택하지 않으며 입력으로만 취급합니다. 오래되었거나 알 수 없는 결정은 기본적으로 compute‑only(주문 게이트 OFF)로 처리합니다.

비목표: 전략 인제스트, DAG diff, 큐/태그 디스커버리(각각 Gateway/DAG Manager 소유). 주문 I/O는 여기에서 다루지 않습니다.

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

`effective_mode` remains the legacy policy string. Gateway/SDK derive an
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
  "ts": "2025-08-28T09:00:00Z"
}
```

Field semantics and precedence
- `freeze=true` overrides `drain`; both imply orders gated OFF.
- `drain=true` blocks new orders but allows existing opens to complete naturally.
- When either `freeze` or `drain` is true, `active` is effectively false (explicit flags provided for clarity and auditability).
- `weight` soft‑scales sizing in the range [0.0, 1.0]. If absent, default is 1.0 when `active=true`, else 0.0.
- `effective_mode` communicates the legacy policy string from WorldService (`validate|compute-only|paper|live`).
- Gateway derives an `execution_domain` when relaying the envelope downstream (ControlBus → SDK) by mapping `effective_mode` as `validate → backtest (orders gated OFF by default)`, `compute-only → backtest`, `paper → dryrun`, `live → live`. `shadow` remains reserved for operator-led validation streams. The canonical ActivationEnvelope schema emitted by WorldService omits this derived field; Gateway adds it for clients so the mapping stays centralized.

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

---

## 5. 보안 & RBAC

- 인증: 서비스 간 토큰(mTLS/JWT); 사용자 토큰은 Gateway에서 WS로 전달
- 권한: 월드 스코프 RBAC는 WS에서 강제; Gateway는 프록시 역할만 수행
- 감사: 모든 쓰기 작업과 평가에 correlation_id를 포함해 로깅

클록 규율(Clock Discipline)
- 결정은 시간에 의존합니다. WS는 단조 증가 서버 클록과 NTP 상태를 강제하며, 허용 가능한 클라이언트 스큐(예: ≤ 2초)를 문서화해야 합니다.

---

## 6. 관측(Observability) & SLO

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

## 7. 장애 모드 & 복구

- WS 다운: Gateway는 캐시된 DecisionEnvelope이 신선할 경우 이를 반환, 아니면 안전 기본값(compute‑only/inactive). Activation은 기본 비활성.
- Redis 손실: 최신 스냅샷에서 Activation을 재구성; 일관성 회복 전까지 주문 게이트 유지.
- 정책 파싱 오류: 해당 버전 거부, 이전 기본값 유지.

---

## 8. 통합 & 이벤트

- Gateway: `/worlds/*` 프록시, TTL 기반 결정 캐시, `--allow-live` 가드 적용
- DAG Manager: 결정과는 독립, 큐/그래프 메타데이터만 연계
- ControlBus: WS는 ActivationUpdated/PolicyUpdated 발행; Gateway가 구독 후 WS를 통해 SDK로 중계

Runner & SDK 통합(명확화)
- SDK/Runner는 실행 모드를 노출하지 않습니다. 호출자는 전략 시작 시 `world_id`만 제공하며, Runner는 WorldService 결정과 활성화 이벤트를 따릅니다.
- DecisionEnvelope의 `effective_mode`는 WS가 계산하며 SDK는 입력으로 취급합니다. 알 수 없거나 오래된 결정은 compute‑only(주문 게이트 OFF)로 처리합니다.
- 제출 시 Gateway는 각 `world_id`에 대해 **WSB upsert**를 보장하며, WVG에 `WorldNodeRef(root)`를 생성/갱신한다.

---

## 9. Testing & Validation

- Contract tests for envelopes (Decision/Activation) using the JSON Schemas (reference/schemas.md).
- Idempotency tests: duplicate/out‑of‑order event handling based on `etag`/`run_id`.
- WS reconcile tests: initial snapshot vs. `state_hash` divergence handling and HTTP fallback.

{{ nav_links() }}

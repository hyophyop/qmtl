---
title: "WorldService — 월드 정책, 결정, 활성화"
tags: [architecture, world, policy]
author: "QMTL Team"
last_modified: 2026-04-03
spec_version: v1.0
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

관련: [Core Loop 계약](../contracts/core_loop.md)  
관련: [월드 라이프사이클 계약](../contracts/world_lifecycle.md)  
관련: [월드 할당 및 리밸런싱 계약](rebalancing_contract.md)  
관련: [Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스](core_loop_world_automation.md)  
관련: [월드 활성화 런북](../operations/activation.md)  
관련: [ACK/Gap Resync RFC (초안)](../design/ack_resync_rfc.md)

!!! note "Risk Signal Hub 연동"
    WorldService는 Risk Signal Hub의 포트폴리오/리스크 스냅샷을 소비하는 제어면 서비스입니다. 토폴로지와 운영 절차는 [Risk Signal Hub](risk_signal_hub.md)와 [Risk Signal Hub 운영 런북](../operations/risk_signal_hub_runbook.md)에서 다룹니다.

운영 규칙:
- 배포 프로필, Redis 요구사항, 기동 전 검증 절차는 [백엔드 퀵스타트](../operations/backend_quickstart.md)와 [배포 경로 결정](../operations/deployment_path.md)에서 관리한다.
- 현재 정책 엔진 구현 범위와 `partial/implemented` 상태는 [QMTL 구현 추적성](implementation_traceability.md)에서 관리한다.

!!! warning "안전 기본값"
- 입력이 모호하거나 부족하면 live로 기본 설정하지 않고 compute-only(backtest)로 강등해야 합니다. `execution_domain`을 비우거나 생략한 WS API 호출이 live로 저장되면 안 됩니다.
- `allow_live=false`(기본)일 때는 운영자가 요청하더라도 활성/도메인이 live로 전환되지 않습니다. 정책 검증(필수 지표, 히스테리시스, dataset_fingerprint 고정)이 통과될 때에만 승격을 허용하세요.
- 클라이언트가 `execution_domain`을 생략하면 월드 노드·검증 캐시는 기본적으로 `backtest`로 저장됩니다. 의도한 도메인을 명시적으로 넣어야 live 범위로 잘못 저장되는 일을 막을 수 있습니다.

!!! note "설계 의도"
- WS는 `effective_mode`(정책 문자열)를 산출하고, Gateway는 이를 `execution_domain`으로 매핑해 공유 컴퓨트 컨텍스트로 전파합니다. SDK/Runner는 모드를 선택하지 않으며 입력으로만 취급합니다. 오래되었거나 알 수 없는 결정은 기본적으로 compute‑only(주문 게이트 OFF)로 처리합니다.
- 제출 메타의 `execution_domain` 값은 참조용 힌트일 뿐이며, 권한 있는 도메인 값은 WS가 산출한 `effective_mode`에서만 파생됩니다.

WorldService의 표면은 다음 경계를 전제로 한다.
- 전략 작성자는 제출과 결과 해석에 집중하고, 정책 평가·활성화 제어는 WS가 소유합니다.
- 월드 수준의 권위 있는 결정과 활성 상태는 WS가 제공합니다.
- live 승격과 자본 적용은 별도 운영 거버넌스 아래 남깁니다.
- 정책/스키마 전환 시에는 장기 병존보다 명시적 마이그레이션 후 단일 모델 수렴을 우선합니다.

비목표:
- 전략 인제스트, DAG diff, 큐/태그 디스커버리(각각 Gateway/DAG Manager 소유). 주문 I/O는 여기에서 다루지 않습니다.
- WorldService/Gateway 없이 Runner/SDK만으로 전체 전략 생애 주기와 최종 평가/게이팅을 처리하는 “순수 로컬 모드”를 정식 운영 모드로 지원하지 않습니다. SDK 레벨의 ValidationPipeline·PnL 헬퍼는 테스트/실험 용도이며, 정책·평가·게이팅의 SSOT는 항상 WorldService입니다.

### 0‑A. Core Loop 정렬 요약

#### 평가·활성화 플로우

- WS 평가 결과(active/weight/contribution/violations)가 **월드 차원의 단일 출처**이며, SDK/Runner는 이를 그대로 사용자에게 노출하고 `ValidationPipeline`은 힌트·로컬 사전 검사 역할로 한정된다.
- `DecisionEnvelope`/`ActivationEnvelope` 스키마와 Runner/CLI `SubmitResult` 구조가 일치하도록 정리해 “전략 제출 → 월드 평가 결과 확인”이 한눈에 이어진다.
- 계약 (정렬 상태)
  - `/worlds/{world_id}/evaluate` → `DecisionEnvelope`/`ActivationEnvelope` 값이 `SubmitResult.ws.decision/activation`에 그대로 매핑됩니다. CLI `--output json`은 WS/Precheck가 분리된 동일 JSON을 출력합니다.
  - 로컬 `ValidationPipeline` 출력은 `SubmitResult.precheck`에만 담기며, `status/weight/rank/contribution`의 SSOT는 WS입니다.
  - `ActivationEnvelope`(`GET/PUT /worlds/{world_id}/activation`) 필드와 `SubmitResult.ws.activation` 필드가 동일 스키마를 사용해 활성/weight/etag/run_id를 노출합니다. `state_hash`는 `/worlds/{world_id}/activation/state_hash`와 ActivationUpdated 이벤트로 제공합니다.

#### ExecutionDomain / effective_mode

- 현재 `/worlds/{world_id}/decide` 정책 경로는 `effective_mode`를 `validate | compute-only | live` 범위에서 산출합니다. Gateway/SDK는 `effective_mode`를 `execution_domain(backtest/dryrun/live/shadow)`로 매핑하며, 활성화/수동 오버라이드 페이로드 호환을 위해 `paper`/`shadow` 토큰도 매퍼에서 허용합니다.
- 제출 메타의 `execution_domain` 값은 참조용 힌트이며 권한 있는 도메인 값은 WS `effective_mode`에서만 파생되고, `world/world.md`, `architecture.md`, `gateway.md`, 본 문서가 동일한 규범(매핑 테이블·우선순위)을 공유한다.

#### 월드 자본 배분 / 리밸런싱

- 리밸런싱 제어면의 상세 규범은 [월드 할당 및 리밸런싱 계약](rebalancing_contract.md)으로 분리되었습니다.
- 본 문서는 submit 결과와 CLI가 최신 allocation snapshot을 **읽기 전용 관측**으로 surfacing 한다는 점, 그리고 plan/apply 경로의 SSOT가 WorldService라는 점만 유지합니다.

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
- Key: world:<id>:activation → { strategy_id|side : { active, weight, etag, run_id, ts } }
- 활성화 상태의 SSOT는 Redis이며, 변경 이력은 감사/복구를 위해 `WorldAuditLog` 엔트리로 기록됩니다.

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
- POST /worlds | GET /worlds | GET /worlds/{world_id} | PUT /worlds/{world_id} | DELETE /worlds/{world_id}

정책(Policies)
- POST /worlds/{world_id}/policies  (upload new version)
- GET /worlds/{world_id}/policies   (list) | GET /worlds/{world_id}/policies/{v}
- POST /worlds/{world_id}/set-default?v=V

바인딩(Bindings)
- POST /worlds/{world_id}/bindings        (upsert WSB: bind `strategy_id` to world)
- GET  /worlds/{world_id}/bindings        (list; filter by `strategy_id`)

목적
- WSB는 각 제출마다 WVG에 `(world_id, strategy_id)` 루트가 존재하도록 보장합니다. 다중 월드를 대상으로 할 경우, 운영 격리와 자원 제어를 위해 월드별 별도 프로세스를 권장합니다.

결정 및 제어
- GET /worlds/{world_id}/decide?as_of=... → DecisionEnvelope
- POST /worlds/{world_id}/decisions       (replace world strategy set via DecisionsRequest)
- GET /worlds/{world_id}/activation?strategy_id=...&side=... → ActivationEnvelope
- GET /worlds/{world_id}/activation/state_hash → activation state hash metadata
- PUT /worlds/{world_id}/activation          (manual override; 요청 본문에 TTL 필드 없음)
- POST /worlds/{world_id}/evaluate           (plan only)
- POST /worlds/{world_id}/apply              (2‑Phase apply; requires run_id)
- GET /worlds/{world_id}/audit               (paginated stream)

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

`effective_mode`는 정책 문자열 그대로 유지됩니다.
`execution_domain`/`compute_context`는 정식 WorldService 스키마 필드가 아니라
Gateway가 부가하는 필드입니다. Gateway는 HTTP 프록시 응답
(`GET /worlds/{id}/decide`, `GET /worlds/{id}/activation`), `/events/subscribe`
activation 부트스트랩 프레임, ControlBus `activation_updated` 릴레이에서
이 필드를 materialize 합니다.

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
- `weight`는 [0.0, 1.0] 범위의 소프트 스케일입니다. WS 활성화 write에서 `weight`를 생략하면 현재 저장소 구현은 `active` 값과 무관하게 `1.0`을 저장하며, 주문 게이트는 별도로 inactive/freeze/drain 상태를 비거래로 처리합니다.
- `effective_mode`는 WorldService 정책 문자열을 담습니다 (`validate|compute-only|paper|live|shadow`).
- Gateway augmentation 경로(`GET /worlds/{id}/activation`, `/events/subscribe` activation bootstrap, ControlBus `activation_updated` 릴레이)에서는 `effective_mode`를 `validate → backtest`, `compute-only → backtest`, `paper → dryrun`, `live → live`, `shadow → shadow`로 매핑한 뒤 `execution_domain`/`compute_context`를 materialize 합니다.
- activation 엔벌로프에는 `as_of`가 없기 때문에 safe-mode 평가에서 `validate|compute-only|paper`처럼 `backtest/dryrun`으로 매핑되는 모드는 `execution_domain=backtest`로 강등될 수 있으며(`compute_context.downgraded=true`, `downgrade_reason=missing_as_of`), 이 메타데이터는 `paper`에만 한정되지 않습니다. `shadow`는 missing-`as_of` 가드로 강등되지 않습니다.
- activation payload에 `effective_mode`가 없으면 Gateway는 fail-closed로 `execution_domain=backtest`를 강제하고 `compute_context.safe_mode=true`, `compute_context.downgraded=true`, `compute_context.downgrade_reason=decision_unavailable`를 설정합니다.
- ControlBus relay 경로에서도 Gateway는 WebSocket fan-out 전에 동일한 매핑/safe-mode 규칙으로 payload를 augmentation 합니다.
- ControlBus 팬아웃 시 [`ActivationEventPublisher.update_activation_state`]({{ code_url('qmtl/services/worldservice/activation.py#L58') }})가 `phase`(`freeze|unfreeze`), `requires_ack`, `sequence`를 주입한다. `sequence`는 [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }})에서 run별 단조 증가 값으로 생성된다.
- `requires_ack=true`의 기본 의미는 Gateway가 해당 `sequence`를 선형 순서로 적용하고 `control.activation.ack`로 `ActivationAck`를 게시하는 것이다(SHALL). 이 ACK는 버스 수신 확인(transport/apply)이며, 개별 SDK/WebSocket 소비자까지의 종단 확인을 뜻하지 않는다.
- Gateway는 선행 `sequence`가 수렴하기 전에는 후속 이벤트(특히 Unfreeze)를 적용하거나 주문 게이트를 열어서는 안 된다(SHALL). 시퀀스 gap 타임아웃·자동 복구 정책은 [ACK/Gap Resync RFC (초안)](../design/ack_resync_rfc.md)에서 정의한다.

아이템포턴시(Idempotency): 컨슈머는 오래된 `etag`/`run_id` 이벤트를 무시해야 합니다(no‑op). 알 수 없거나 만료된 결정/활성화는 “비활성/안전” 상태로 간주합니다.

TTL 및 신선도(Staleness)
- DecisionEnvelope에는 TTL이 포함됩니다(미지정 시 기본 300초). TTL 경과 후 Gateway는 결정을 오래된 상태로 간주하고, 새 결정을 받을 때까지 안전 기본값인 compute‑only(주문 게이트 OFF)를 강제해야 합니다.
- Activation에는 TTL이 없고 `etag`를 포함합니다. 알 수 없거나 만료된 활성화 → 주문 게이트 OFF.
- `state_hash`는 `GET /worlds/{world_id}/activation/state_hash`와 ActivationUpdated 이벤트로 제공되며 divergence 확인에 사용됩니다.

---

### 4. Execution Domains & Apply (normative)

- Domains: `backtest | dryrun | live | shadow`.
- Isolation invariants:
  - Cross‑domain edges MUST be disabled by default via `EdgeOverride` until a policy explicitly enables them post‑promotion.
  - Orders are always gated OFF while `freeze=true` during 2‑Phase apply.
  - Domain switch is atomic from the perspective of order gating: `Freeze/Drain → Switch(domain) → Unfreeze`.
  - ActivationUpdated ACK 수렴 절차:
    - Freeze/Drain 및 Unfreeze 단계 이벤트는 `requires_ack=true`, `phase`, `sequence` 메타데이터가 포함된 ControlBus 메시지로 게시된다.
    - Gateway는 `sequence` 기준으로 선형 재생을 보장하고, 선행 `sequence`가 처리되기 전에는 동일 run의 후속 이벤트(특히 Unfreeze)를 전파하거나 주문 게이트를 해제해서는 안 된다(SHALL).
    - ACK는 ControlBus 응답 채널로 보고되며, payload에 `world_id`, `run_id`, `sequence`, `phase`를 포함해야 한다. run별 단조 증가를 유지하고 역순 ACK는 무시하거나 경고해야 한다(SHOULD). 현재 WS apply 완료 조건은 ACK 스트림을 하드 게이트로 사용하지 않는다.
- 2‑Phase Apply protocol (SHALL):
  1. **Freeze/Drain** — Activation entries set `active=false, freeze=true`; Gateway/SDK gate all order publications; EdgeOverride keeps live queues disconnected.
  2. **Switch** — ExecutionDomain updated (예: backtest→live), queue/topic bindings refreshed, Feature Artifact snapshot pinned via `dataset_fingerprint`.
  3. **Unfreeze** — WS는 Switch 이후 `freeze=false` 이벤트를 게시한다. Gateway/SDK는 해당 unfreeze `sequence`를 적용하고 ACK를 게시하기 전까지 주문 게이트를 유지한다(SHALL).
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

## 5. 할당 & 리밸런싱 제어면

WorldService는 allocation snapshot, rebalancing plan/apply, ControlBus 이벤트의 SSOT를 유지하지만,
상세 표면 계약은 [월드 할당 및 리밸런싱 계약](rebalancing_contract.md)으로 분리했습니다.

이 문서에서 유지하는 규범 경계:

- submit/CLI가 읽는 allocation snapshot의 권위 있는 출처는 WorldService입니다.
- `/allocations`, `/rebalancing/plan`, `/rebalancing/apply`는 run_id/etag 기반 감사 추적을 공유합니다.
- schema version/alpha metrics handshake와 `rebalancing_planned` fan-out도 같은 제어면 계약의 일부입니다.

상세 API 스키마, 멱등성 규칙, 운영 전환 절차는 다음 문서를 봅니다.

- [월드 할당 및 리밸런싱 계약](rebalancing_contract.md)
- [리밸런싱 실행 어댑터](../operations/rebalancing_execution.md)
- [Rebalancing Schema Coordination](../operations/rebalancing_schema_coordination.md)

---

## 6. 보안 & RBAC

- 인증/권한/감사는 WorldService 경계에서 강제합니다. Gateway는 프록시일 뿐, 월드 스코프 RBAC와 쓰기 감사의 권위는 WS에 있습니다.
- 결정과 apply는 시간 민감 경로이므로 단조 증가 서버 클록과 NTP 정상 상태를 전제합니다.
- 실제 override/apply 운영 절차는 [월드 활성화 런북](../operations/activation.md)과 [World Validation 거버넌스](../operations/world_validation_governance.md)에서 다룹니다.

---

## 7. 관측(Observability) & SLO

- WorldService는 apply, allocation snapshot, validation worker, Risk Hub 소비, 도메인 격리 관련 메트릭의 출처입니다.
- 운영 경보, 대시보드, SLO 임계값은 [모니터링 및 알림](../operations/monitoring.md)에서 관리합니다.
- 리밸런싱 실행/팬아웃 지표는 [리밸런싱 실행 어댑터](../operations/rebalancing_execution.md)와 함께 해석합니다.

---

## 8. 장애 모드 & 복구

- WS 다운: Gateway는 캐시된 DecisionEnvelope이 신선할 경우 이를 반환, 아니면 안전 기본값(compute‑only/inactive). Activation은 기본 비활성.
- Redis 손실: `WorldAuditLog`의 activation/apply 엔트리를 재생해 Activation을 재구성하고, 일관성 회복 전까지 주문 게이트를 유지.
- 정책 파싱 오류: 해당 버전 거부, 이전 기본값 유지.

복구 절차와 운영 체크리스트는 [월드 활성화 런북](../operations/activation.md)과 [모니터링 및 알림](../operations/monitoring.md)에서 다룹니다.

---

## 9. 통합 & 이벤트

- Gateway: `/worlds/*` 프록시, TTL 기반 결정 캐시, `--allow-live` 가드 적용
- DAG Manager: 결정과는 독립, 큐/그래프 메타데이터만 연계
- ControlBus: WS는 ActivationUpdated/PolicyUpdated를 발행하고 Gateway가 구독해 SDK로 중계합니다. activation 릴레이는 fan-out 전에 `execution_domain`/`compute_context` augmentation을 거치며, `/events/subscribe` activation 부트스트랩 프레임도 같은 augmentation 경로를 사용합니다.
- campaign tick/live promotion 거버넌스는 [Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스](core_loop_world_automation.md)에서 별도로 다룹니다.

Runner & SDK 통합(명확화)
- SDK/Runner는 실행 모드를 노출하지 않습니다. 호출자는 전략 시작 시 `world_id`만 제공하며, Runner는 WorldService 결정과 활성화 이벤트를 따릅니다.
- DecisionEnvelope의 `effective_mode`는 WS가 계산하며 SDK는 입력으로 취급합니다. 알 수 없거나 오래된 결정은 compute‑only(주문 게이트 OFF)로 처리합니다.
- 제출 시 Gateway는 각 `world_id`에 대해 **WSB upsert**를 보장하며, WVG에 `WorldNodeRef(root)`를 생성/갱신한다.

---

## 10. Testing & Validation

- envelope, activation, rebalancing 표면의 대표 테스트 근거는 [QMTL 구현 추적성](implementation_traceability.md)에서 관리합니다.
- 운영 수준의 검증 절차는 [End-to-End Testing](../operations/e2e_testing.md)과 [백엔드 퀵스타트](../operations/backend_quickstart.md)의 smoke 절차를 따릅니다.

{{ nav_links() }}

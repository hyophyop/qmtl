---
title: "아키텍처 용어집"
tags: [architecture, glossary]
author: "QMTL Team"
last_modified: 2025-11-22
---

{{ nav_links() }}

# 아키텍처 용어집

## 0. 목적과 Core Loop 상 위치

- 목적: QMTL 아키텍처 전반에서 사용하는 핵심 용어(DecisionEnvelope, ExecutionDomain, GSG/WVG 등)를 한 곳에 모아 정의합니다.
- Core Loop 상 위치: Core Loop 각 단계에서 등장하는 개념을 **일관된 용어로 연결하는 참고 사전** 역할을 하며, 다른 설계 문서를 읽을 때 공통 배경을 제공합니다.
- DecisionEnvelope: 월드 결정 결과로 `world_id`, `policy_version`, `effective_mode`, `reason`, `as_of`, `ttl`, `etag`를 포함합니다.
- effective_mode: DecisionEnvelope의 정책 결과 문자열. 값: `validate | compute-only | paper | live`. 소비자는 계산/라우팅을 위해 ExecutionDomain으로 매핑해야 합니다(아래 규범 참조).
- execution_domain: Gateway/SDK가 `effective_mode`를 매핑한 파생 필드 (`backtest | dryrun | live | shadow`). SDK로 중계되는 봉투(envelope)에 유지됩니다. 제출자의 `meta.execution_domain`은 힌트이며, 권한 있는 값은 WS `effective_mode`에서만 파생됩니다. Runner/SDK는 `shadow`를 백테스트로 강등하지 않고 유지하되 주문 발행은 하드 차단합니다.
- ActivationEnvelope: `(world_id, strategy_id, side)`에 대한 활성화 상태. `active`, `weight`, `etag`, `run_id`, `ts`, 선택적 `state_hash` 포함.
- ControlBus: 버전이 명시된 제어 이벤트(ActivationUpdated, QueueUpdated, PolicyUpdated)를 운반하는 내부 제어 버스(Kafka/Redpanda). 공개 API가 아닙니다.
- EventStreamDescriptor: Gateway가 발급하는 불투명(opaque) WS 디스크립터 (`stream_url`, `token`, `topics`, `expires_at`, 선택적 `fallback_url`, `alt_stream_url`).
- etag: 중복 제거 및 동시 업데이트 검증에 사용되는 단조 증가 버전 식별자.
- run_id: 2‑단계 Apply 작업의 멱등성 토큰.
- TTL: 캐시 유효 기간(DecisionEnvelope 기준).
- data_currency: `now`와 `data_end` 비교로 초기 모드를 선택하는 신선도 정책.
- state_hash: 활성화 스냅샷의 해시(선택). 저비용으로 분기(divergence) 감지.

- Global Strategy Graph (GSG): Content‑addressed, deduplicated global DAG of strategies and nodes; immutable/append‑only SSOT owned by DAG Manager.
- World View Graph (WVG): 월드‑로컬 메타데이터(상태, 검증, 결정)를 가진 GSG 참조 오버레이. 변이 가능한 SSOT이며 WorldService 소유.
- NodeID: 노드의 정규 형태에 대한 결정적 BLAKE3 해시: `(node_type, interval, period, params(canonical, split), dependencies(sorted), schema_compat_id, code_hash)`. `schema_compat_id`는 스키마 레지스트리의 메이저 호환 식별자이며, 마이너/패치 호환 변경은 동일 식별자를 유지해 `node_id`를 보존합니다.
- schema_compat_id: NodeID 정규화에 사용되는 메이저 호환 식별자. `schema_id`와는 구분됩니다.
- schema_id: 조회/해결을 위한 구체적 스키마 레지스트리 식별자. 마이너/패치 변경으로 바뀔 수 있으나 `schema_compat_id`에는 영향 없음.
- EvalKey: 월드‑로컬 검증 캐시 키용 BLAKE3 해시: `(NodeID || WorldID || ExecutionDomain || ContractID || DatasetFingerprint || CodeVersion || ResourcePolicy)`; 도메인 스코프 검증으로 백테스트/라이브 캐시 혼합을 방지.
- WorldNodeRef: `(world_id, node_id, execution_domain)` scoped record storing world‑/도메인‑로컬 `status`, `last_eval_key`, and annotations.
- DecisionsRequest: API payload replacing the per-world strategy set; contains an ordered list of unique, non-empty strategy identifiers persisted by WorldService.
- SSOT boundary: DAG Manager owns GSG only; WorldService owns WVG only. Gateway proxies/caches; it is not an SSOT.

## 실행 도메인과 격리(Execution Domain & Isolation)

- ExecutionDomain: 월드의 실행 컨텍스트. `backtest | dryrun | live | shadow` 중 하나이며, 게이팅/큐 라우팅/검증 범위를 좌우합니다.
- 도메인 스코프 ComputeKey: DAG Manager/런타임에서 사용하는 내부 중복 제거/캐시 키: `ComputeKey = blake3(NodeHash ⊕ world_id ⊕ execution_domain ⊕ as_of ⊕ partition)`. NodeID는 월드 무관성을 유지하며, ComputeKey가 도메인/월드 격리를 보장합니다.
- EdgeOverride (WVG scope): World‑local reachability control per edge; used to disable cross‑domain paths (e.g., backtest graph → live queues) until policy‑driven enablement. Implemented by [`EdgeOverrideRepository`]({{ code_url('qmtl/services/worldservice/storage/edge_overrides.py#L13') }}) and surfaced via the WorldService [`/worlds/{world_id}/edges/overrides`]({{ code_url('qmtl/services/worldservice/routers/worlds.py#L109') }}) API.
- 2‑Phase Apply: WorldService operation ensuring safe domain switches: `Freeze/Drain → Switch(domain) → Unfreeze`. Orders are gated OFF while `freeze=true`.
- Feature Artifact: Immutable output of the Feature Plane identified by `(factor, interval, params, instrument, t, dataset_fingerprint)`. Shared read-only across ExecutionDomains.
- dataset_fingerprint: 검증/프로모션에 사용된 데이터 스냅샷을 나타내는 토큰. 정책과 EvalKey에 반드시 포함됩니다.
- share_policy: 아티팩트 재사용 방식을 제어하는 정책 플래그. `feature-artifacts-only`는 런타임 캐시 공유를 금지하고 읽기 전용 소비를 강제합니다.
- cross_context_cache_hit_total: 라벨이 다른 `(world_id, execution_domain, as_of, partition)` 조합으로 캐시 히트가 발생했을 때 증가하는 카운터. 반드시 0을 유지해야 합니다.

실행 모드 → ExecutionDomain 매핑(규범)
- `validate` → `compute-only`와 동일하며 오더 게이트 OFF; 기본은 `backtest`(운영자가 명시적으로 `shadow`를 요청하지 않는 한)
- `compute-only` → `backtest`
- `paper`/`sim` → `dryrun`
- `live` → `live`
- `offline`/`sandbox` 등 기타 모호 토큰은 backtest로 강등

<a id="shadow-execution-domain"></a>
### Shadow execution_domain 병렬 진행 합의
- 공통 계약: `shadow`는 라이브 입력 미러이며 주문 발행은 하드 차단, 도메인/네임스페이스는 격리됩니다. 제출자의 `meta.execution_domain=shadow`는 힌트일 뿐이며, 권한 값은 WS `effective_mode`에서 파생합니다.
- 필드/태그/에러 정합: `execution_domain=shadow`를 Runner/SDK/Gateway/WS 전 경로에서 유지하고 ComputeKey/EvalKey/캐시(arrow 포함), ControlBus/WebSocket 릴레이, 메트릭/히스토리/태그 쿼리 매핑 모두에 동일 라벨을 적용합니다. 주문 경로는 shadow에서 무시 또는 명시적으로 거부합니다.
- 테스트 책임 분리: Runner/SDK는 섀도우 제출 시 큐/노드 실행, 주문 미발행, 캐시 키 포함 여부를 검증합니다. Gateway/WS는 제출·컨텍스트 패스스루, 릴레이 태깅, 태그 쿼리/큐 맵 테스트와 운영자 문서 업데이트를 맡습니다.
- 머지/연동: 섀도우 도메인 관련 작업은 Runner/SDK와 Gateway/WS에서 병렬 진행 가능하며, 양쪽 반영 후 end-to-end 섀도우 경로 점검을 권장합니다.

보조 용어
- as_of: 결정적 리플레이를 위해 백테스트를 고정 입력 뷰에 묶는 데이터 스냅샷 타임스탬프 또는 커밋 ID.
- partition: 멀티테넌트 실행 범위를 지정하기 위해 ComputeKey에 포함되는 선택적 파티션 키(테넌트/포트폴리오/전략).
- NodeHash: NodeID 파생에 사용되는 정규 해시 입력(정규 노드 형식의 blake3 다이제스트).
- WSB (WorldStrategyBinding): 제출 시 Gateway가 생성하는 `(world_id, strategy_id)` 연관으로 루트 `WorldNodeRef` 존재를 보장.

{{ nav_links() }}

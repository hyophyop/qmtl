멋지게 반영하셨어요. 저장소를 보면 docs/architecture/ 아래에 최상위 설계 문서가 생겼고(예: docs/architecture/architecture.md), 루트 README.md에서도 Gateway → DAG Manager(중복 제거/스케줄링) → WorldService(SSOT), ControlBus(WebSocket 이벤트) 축과 문서 체계를 안내하고 있어요. 이 방향은 우리가 논의한 명시적 격리 + 엔진 레벨 원천 차단을 담기 좋은 틀입니다.  ￼ 또한, QMTL의 DAG·슬라이딩 윈도우·백테스트/드라이런/라이브 모드와 노드 재사용 철학은 기존 분석서와 일관됩니다.  ￼

아래는 (1) 잘 잡힌 부분, (2) 누락·보완 포인트(체크리스트), (3) 바로 붙일 수 있는 문서 패치 조각(diff 수준), (4) 리스크 시나리오 & 검증 기준 순서입니다.

⸻

(1) 잘 잡힌 부분 (현재 문서 구조 기준)
	•	문서 물리적 위치/역할 분리: docs/architecture/ 경로로 상위 설계 문서가 분리됨 → 정책/운영 문서와 참조되기 좋음.  ￼
	•	컴포넌트 축 명시: README가 Gateway/DAG Manager/WorldService/ControlBus 3+1축을 상단에서 요약(설계 관통 개념). CLI(dagmanager diff, neo4j-init, gw --help)와 참조 문서 링크도 안내.  ￼
	•	거래 파이프라인 요소 표기: RiskManager/TimingController/Execution modeling/Order publishing 등 최신 노드군을 전면에 배치(백테스트 정합성·게이팅 설계에 필수).  ￼
	•	문서 대시보드 신호: docs/dashboard.json 언급으로 문서 상태 트래킹 기반 마련.  ￼
	•	핵심 철학 서술과 일치: DAG 부분 재사용·슬라이딩 윈도우·모드 전환은 기존 분석서와 개념 정합.  ￼

⸻

(2) 누락·보완 포인트 체크리스트

다음 항목이 명세(“must/shall”) 수준으로 문서에 박혀 있어야 백테스트↔라이브 오염을 원천 차단할 수 있습니다. 파일/섹션 권장 위치를 함께 적었습니다.

A. ExecutionDomain 1급 개념 & WorldNodeRef 확장 (WVG)
	•	해야 할 일: WorldNodeRef = (world_id, node_id, execution_domain)를 정의/예시/제약까지 명문화.
	•	제약: (shall) 서로 다른 execution_domain 간 상태/큐/토픽 공유 금지.
	•	토픽 네임스페이스: {world}.{domain}.{node} + ACL 규칙(교차 발행/구독 금지, 허용 예외 무).
	•	권장 위치: docs/architecture/architecture.md의 WorldService/WVG 절 혹은 별도 wvg.md.
	•	근거: 운영 레이어에서의 명시적 격리가 첫 방어선.  ￼

B. Domain‑Scoped ComputeKey (엔진 레벨 격리)
	•	해야 할 일: DAG Manager의 중복 제거/캐시 키를
ComputeKey = hash(node_def) ⊕ salt(world_id, execution_domain, as_of, partition)
로 정의(NodeID는 호환 유지).
	•	제약: (shall) ComputeKey의 상기 4축이 다르면 캐시·스케줄 분리.
	•	권장 위치: dag_manager.md 또는 architecture.md 내 Deduplication/Cache 절.
	•	근거: 재사용을 엔진 차원에서 차단 · 이행 리스크 최소화(호환 유지).  ￼

C. 2‑Phase Apply(Freeze→Switch→Unfreeze) 프로토콜
	•	해야 할 일: 상태 전이도(시퀀스) + 원자성/멱등성 규칙 + 실패 시 롤백 표준화.
	•	Freeze 기간: (shall) 모든 Activation active=false, freeze=true, 주문 게이트 완전 차단.
	•	Switch: (shall) execution_domain: backtest→live 전환, 토픽 리바인딩.
	•	Unfreeze: (shall) 새 도메인에서만 재개.
	•	권장 위치: gating_apply.md 신설.
	•	근거: 전환 중 혼합 경로 차단(EdgeOverride와 함께).  ￼

D. EdgeOverride 운영 규칙
	•	해야 할 일: 승격 전 백테스트 WVG → 라이브 토픽 향하는 에지 (shall) 강제 비활성. 승격 완료 후 정책으로만 해제.
	•	권장 위치: wvg.md 혹은 gating_apply.md에 알고리즘 스텝으로.  ￼

E. EvalKey & DatasetFingerprint
	•	해야 할 일: EvalKey ⊇ {execution_domain, dataset_fingerprint, params...} 명시, 교차 도메인 검증 캐시 공유 금지.
	•	권장 위치: validation.md.  ￼

F. Feature Artifact Store (Dual‑Plane)
	•	해야 할 일:
	•	Feature Plane: (shall) 불변 아티팩트 (factor, interval, params, instrument, t, dataset_fingerprint) 머티리얼라이즈.
	•	공유 원칙: 도메인 간 공유는 런타임 캐시가 아닌 읽기 전용 아티팩트만 허용.
	•	Retention/Backfill/버전 규칙·스토리지 백엔드(파일/RocksDB/객체스토리지) 표기.
	•	권장 위치: dual_plane.md.  ￼

G. Clock/API 가드
	•	해야 할 일: 백테스트 (shall) VirtualClock 전용, 라이브 (shall) WallClock 전용. 혼용 호출은 컴파일 에러.
	•	입력 노드: 백테스트 (shall) as_of 강제.
	•	권장 위치: sdk_contracts.md 또는 architecture.md의 Time/Clock 절.  ￼

H. 관측 & SLO
	•	해야 할 일:
	•	(SLO) cross_context_cache_hit == 0 미충족 시 실행 차단.
	•	dagmanager diff와 drift 리포트(feature/signal/fill) 의무화.
	•	WorldAuditLog에 게이팅 이벤트 타임라인(requested/approved/promoted/rolled_back).
	•	권장 위치: observability.md(CLI 연동도 함께).  ￼

I. Gating Policy 스키마(롱/숏 완전 분리, can_short 명시)
	•	해야 할 일: 정책 YAML에 롱/숏 파라미터 분리·can_short: true·슬리피지/수수료/Execution 모델을 명세 수준으로.
	•	권장 위치: gating_policy.md. (샘플 아래 “패치 조각” 참조)

J. ADR(Architecture Decision Record) 트랙
	•	해야 할 일: docs/architecture/adr/에 ExecutionDomain, ComputeKey, Dual‑Plane 등 결정 기록 추가.
	•	권장 위치: adr/0001-execution-domain.md 등. (레퍼런스 링크 포함)  ￼

위 A~J는 현 문서가 방향성을 갖고 있는 만큼(구조/명칭/CLI 노출), 이제 “명세화”의 깊이만 채우면 완성도 급상승입니다.  ￼  ￼

⸻

(3) 바로 붙일 수 있는 문서 패치 조각

3‑1. architecture.md → 격리 불변식(표준 문구)

### Execution Isolation Invariants

**I1. Domain-Scoped State:** Any node state, queue binding, or topic under `{world}.{domain}.{node}` SHALL be accessible only within the same `{world, domain}`. Cross-domain access is forbidden.

**I2. Engine-Level Separation:** The DAG Manager SHALL compute a `ComputeKey` for deduplication and caching:
`ComputeKey = hash(node_def) ⊕ salt(world_id, execution_domain, as_of, partition)`.
If any salt component differs, results SHALL NOT be reused.

**I3. Snapshot & Clocks:** Backtests SHALL use VirtualClock and data `as_of` snapshots; Live SHALL use WallClock. Mixing clocks within a single plan is a compile-time error.

**I4. Artifact-Only Sharing:** Cross-domain reuse is allowed only for immutable feature artifacts keyed by `(factor, interval, params, instrument, t, dataset_fingerprint)`. Runtime caches MUST NOT be shared across domains.

3‑2. dag_manager.md → ComputeKey 명세

#### ComputeKey
- `node_def`: code+params+upstreams logical hash (stable).
- `salt`   : tuple `{world_id, execution_domain, as_of, partition}`.
- Rule     : if `salt` differs → schedule/caches are disjoint.
- Backward compatibility: NodeID remains unchanged; only the deduplication key is extended.

3‑3. wvg.md → WorldNodeRef & 토픽/ACL

WorldNodeRef := (world_id, node_id, execution_domain)

Topic naming := "{world_id}.{execution_domain}.{node_id}"
ACL          := allow if and only if same {world_id, execution_domain}

3‑4. gating_apply.md → 2‑Phase Apply

1) Freeze:
   - Activation: active=false, freeze=true
   - Order gates closed; EdgeOverride disables edges to live topics
2) Switch:
   - execution_domain: backtest → live
   - Rebind topics to "{world}.live.{node}"
3) Unfreeze:
   - Activation: active=true, freeze=false (live only)
Failure handling:
   - Idempotent retries; on error → rollback to prior domain and re-enable overrides.
Audit:
   - Emit events: gating.{requested|approved|promoted|rolled_back}

3‑5. dual_plane.md → Feature Artifact Store

Feature Artifact Key:
(factor, interval, params, instrument, t, dataset_fingerprint)

Policies:
- Immutable, versioned; retention/backfill documented.
- Cross-domain reads allowed (read-only); runtime caches never shared.
Backends: file / object storage / RocksDB (read-only mounts in live).

3‑6. validation.md → EvalKey

EvalKey := { execution_domain, dataset_fingerprint, strategy_params_hash, window_spec, ... }
Rule: Eval caches SHALL NOT be shared across domains.

3‑7. gating_policy.md → 정책 YAML(롱/숏 분리 + can_short)

gating_policy:
  promotion_point: "2025-10-01T00:00:00Z"
  apply: { mode: two_phase, freeze_timeout_ms: 30000 }
  domains: { from: backtest, to: live }
  clocks:
    backtest: { type: virtual, epoch0: "2020-01-01T00:00:00Z" }
    live:     { type: wall }
  dataset_fingerprint: "ohlcv:ASOF=2025-09-30T23:59:59Z"

  share_policy: "feature-artifacts-only"   # runtime cache sharing: forbidden
  snapshot: { strategy_plane: "cow", feature_plane: "readonly" }

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

3‑8. observability.md → CLI 연계 문구
	•	qmtl service dagmanager diff --file dag.json --dry-run로 게이트 전/후 그래프 차이 확인.
	•	문서 현황은 docs/dashboard.json으로 트래킹.  ￼

3‑9. adr/0001-execution-domain.md (요지)
	•	결정: ExecutionDomain을 WVG 1급 개념으로 채택, 토픽 네임스페이스/ACL 강제.
	•	결과: 도메인 간 상태·큐·캐시 오염 방지, 게이팅 안전성↑. (ADR 템플릿 레퍼런스)  ￼

⸻

(4) 리스크/시나리오 & 검증 기준
	•	긍정: A~H가 문서에 “shall”로 고정되면, 백테스트 재현성과 게이팅 안전성이 명세 수준에서 보장되고, Feature 아티팩트 재사용으로 계산비도 절감.  ￼
	•	중립: ComputeKey·Artifact 도입으로 초기 운영 복잡도↑ → 문서에 백엔드 선택 가이드/운영 플레이북 보강 권장.
	•	부정(극단): 도메인/토픽 오배선이나 as_of 누락이 생기면 즉시 오염 가능 → (shall) cross_context_cache_hit==0 미충족 시 실행 차단을 SLO로 문서화.

⸻

한 줄 요약

문서에 이미 틀은 잘 깔렸습니다(컴포넌트·CLI·파일 체계). 이제 ExecutionDomain/WVG·ComputeKey·2‑Phase Apply·Artifact Store·Clock 가드·SLO 6가지를 명세(shall)와 예시로 못 박으면, 백테스트 격리와 라이브 게이팅이 설계→운영→검증 전 구간에서 닫힙니다. 필요한 문구/예시는 위 “패치 조각”을 그대로 붙이시면 됩니다.  ￼  ￼

원하시면, 각 문서 파일의 현재 목차에 맞춰 위 조각을 PR 형태의 diff로 재구성해 드릴게요(롱/숏 파라미터 분리와 can_short: true 포함).
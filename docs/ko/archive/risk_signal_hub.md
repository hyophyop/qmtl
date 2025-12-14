---
title: "Risk Signal Hub 설계 (초안)"
tags: [design, risk, signals, snapshots]
author: "QMTL Team"
last_modified: 2025-12-09
status: draft
---

# Risk Signal Hub 설계 (초안)

!!! abstract "목적"
    `risk_signal_hub`은 **포트폴리오/리스크 스냅샷과 리스크·exit 신호의 단일 진실 소스**를 제공한다.  
    실행/배분(gateway)에서 생성되는 가중치·공분산·실현 리턴·스트레스 결과를 표준화해 저장하고,  
    WorldService/Exit Engine/모니터링이 동일한 스냅샷을 읽어 **일관된 검증·exit·모니터링**을 수행하도록 한다.

연관 문서:
- Core Loop × WorldService 로드맵: [design/core_loop_world_roadmap.md](../design/core_loop_world_roadmap.md)
- WorldService 평가 런 & 메트릭 API: [design/worldservice_evaluation_runs_and_metrics_api.md](../design/worldservice_evaluation_runs_and_metrics_api.md)
- World 검증 v1 구현 계획: [design/world_validation_v1_implementation_plan.md](../design/world_validation_v1_implementation_plan.md) §6
- Exit Engine 개요: [design/exit_engine_overview.md](../design/exit_engine_overview.md)
- World Validation 아키텍처: [design/world_validation_architecture.md](../design/world_validation_architecture.md)

---

## 0. 요구사항 요약

- **SSOT**: 포트폴리오 상태(가중치/공분산/스트레스/실현 리턴)와 리스크 신호를 한 곳에서 관리.
- **느슨한 결합**: 실행(gateway)은 스냅샷을 기록/발행만, 소비자(WS, exit 엔진)는 읽기 전용.
- **재현성**: as_of/version/hash로 동일 스냅샷을 재현 가능.
- **성능/확장성**: 이벤트 + 머티리얼라이즈드 뷰 형태, 큰 데이터는 ref/id로 전달.
- **보안/감사**: 쓰기 주체 제한, 모든 변경에 감사/서명 가능하도록 메타 포함.

### 0.1 Core Loop 로드맵과의 정렬(의도)

이 문서의 `risk_signal_hub`는 “WorldService가 월드 정책/결정/검증을 일관되게 수행하기 위한 입력 SSOT”를 제공한다.

- **Core Loop 로드맵(Phase 2)**: Evaluation Run은 “월드 내 제출/평가 사이클”을 추적하는 1급 개념이다. 이때 리스크/포트폴리오 스냅샷(가중치·공분산·실현 리턴·스트레스)은 본문에서 정의한 `risk_signal_hub`를 통해 **버전/해시/`as_of`가 고정된 참조(ref)**로 연결되는 것을 목표로 한다.
- **Core Loop 로드맵(Phase 5)**: “검증 단계 고도화(리스크 컷/스트레스/데이터 신선도)”는 `risk_signal_hub`가 제공하는 최신/버전 고정 스냅샷을 입력으로 사용해 **WS/Exit Engine/모니터링이 동일한 근거 데이터**를 공유하도록 정렬한다.

### 0.2 v1 기본 결정(권장 기본값)

- TTL: `ttl_sec`의 기본값은 **900초(15m)** 로 한다. (`ttl_sec` 미지정 시 서버가 900으로 채움)
  - 상한: 운영 실수 방지를 위해 과도한 TTL(예: `ttl_sec > 86400`)은 422로 거절한다.
- 버전 충돌: `(world_id, version)`은 전역 유일을 전제로 하며, 충돌은 **기본 409(거절)** 로 처리한다. (덮어쓰기는 v1에서 금지)
- 멱등/중복 제거(dedupe):
  - `dedupe_key = (world_id, version, hash, actor, stage)`
  - 동일 `dedupe_key` 재전송은 성공(멱등)으로 처리하고, 서버는 `risk_hub_snapshot_dedupe_total`로 계수한다.
  - `(world_id, version, actor, stage)`가 같은데 `hash`가 달라지면 409로 거절한다. (같은 버전에서 내용이 바뀐 것으로 취급)
- 대용량 ref(공분산/리턴): `*_ref`는 v1에서는 **opaque string(URI 또는 키)** 로 유지하되,
  - 소비자는 `hash`/`version`/`as_of`로 무결성과 재현성을 검증할 수 있어야 한다.
  - blob TTL은 snapshot TTL 이상이어야 한다(최소 `ttl_sec`).

---

## 1. 스키마/계약 (v1 초안)

### 1.1 스냅샷 페이로드
```json
{
  "world_id": "world-1",
  "as_of": "2025-01-15T00:00:00Z",
  "version": "v20250115T0000Z",
  "weights": {"strat_a": 0.35, "strat_b": 0.25, "strat_c": 0.40},
  "covariance_ref": "cov/2025-01-15",
  "covariance": {"strat_a,strat_b": 0.12, "strat_b,strat_c": 0.15},
  "realized_returns_ref": "s3://.../realized/2025-01-15.parquet",
  "stress": {"crash": {"dd_max": 0.30, "es_99": 0.25}},
  "constraints": {"max_leverage": 3.0, "adv_util_p95": 0.25},
  "provenance": {"source": "gateway", "cov_version": "v42"},
  "hash": "blake3:...",
  "ttl_sec": 900
}
```

- 필수: `world_id`, `as_of`, `version`, `weights`
- 선택: `covariance_ref`(권장), `covariance`(작을 때 inline), `realized_returns_ref`, `stress`, `constraints`
- 메타: `provenance.source/cov_version`, `hash`, `ttl_sec`

### 1.1.1 헤더·메타 계약
- 쓰기 요청 헤더:
  - `Authorization: Bearer <token>` (prod 필수)
  - `X-Actor`: 작성 주체(필수)
  - `X-Stage`: 검증/배포 스테이지(backtest/paper/live 등, 가능하면 필수)
- 스냅샷 `provenance` 채우기:
  - `provenance.actor` ← `X-Actor`
  - `provenance.stage` ← `X-Stage` (없으면 `unknown` 취급, dedupe/메트릭 분리 불가)
  - `provenance.reason/source/schema_version` 등은 프로듀서에서 설정
- TTL: `ttl_sec` 기본 900초(15m). 만료 스냅샷은 소비자가 거부하고 `risk_hub_snapshot_expired_total`에 계수.
- Idempotency/dedupe:
  - `dedupe_key = (world_id, version, hash, actor, stage)` 조합으로 dedupe 처리(`risk_hub_snapshot_dedupe_total`에 계수).
  - 동일 `dedupe_key` 재전송은 멱등 성공으로 처리한다.
  - `(world_id, version)` 충돌은 기본 409로 거절한다(덮어쓰기 금지).

### 1.2 이벤트 목록
- `PortfolioSnapshotUpdated` (필수 필드: world_id, version, as_of, weights, covariance_ref/hash, ttl)
- `CovarianceUpdated` (covariance_ref/hash, as_of, version)
- `RealizedReturnsIngested` (ref, as_of, horizon)
- `StressResultsUpdated` (stress payload 또는 ref)
- `ExitSignalEmitted` (exit 엔진이 발행; 전략/월드별 exit 권고, 사유/지표)

페이로드는 큰 데이터(리턴/공분산)를 ref/id로 전달하고, 소비자는 ref로 원본 스토리지를 조회.

---

## 2. 저장/조회 뷰

- 저장소(템플릿):
  - Dev/경량: 인메모리/SQLite에 메타·버전 저장, 캐시/오프로드는 fakeredis/인메모리만 사용(실 Redis/S3/File 영속 스토리지는 dev에서 비활성). 공분산 등은 inline(또는 fakeredis ref)으로만 검증용 최소 구성.
  - Prod: Postgres(메타/버전/감사) + Redis/KeyDB(최신 스냅샷 캐시) + 오브젝트 스토리지(S3/OBS/GCS; 공분산/리턴 시계열 ref) + Kafka/ControlBus(이벤트).
  - 선택: ClickHouse/BigQuery 등 컬럼형 DB에 시계열을 적재하고 ref로 연결.
  키: `(world_id, version)` 또는 `(world_id, as_of)`; 큰 데이터는 ref/id로 저장.
- 조회 API(내부):
  - `get_snapshot(world_id, version=None, as_of=None)` → 최신 또는 특정 버전 반환
  - `list_snapshots(world_id, limit=N, since=ts)`
- 데이터 크기 이슈: 공분산/리턴 시계열은 object storage/DB에 저장, 스냅샷에는 `ref`만 포함. 조회 시 ref를 따라가거나 WS/exit 엔진은 요약(σ, ρ)만 사용.

---

## 3. 접근 제어/감사

- 쓰기: gateway/리스크 엔진 계정만 허용.
- 읽기: WS, exit 엔진, 모니터링.
- 감사: 모든 이벤트/쓰기 연산에 `actor`, `ts`, `hash` 기록. 필요 시 서명/체크섬 검증.

---

## 4. 소비자 통합 포인트

- WS ExtendedValidationWorker: `get_snapshot`으로 weights/covariance/stress를 읽어 Var/ES/Sharpe 베이스라인 계산.
- Exit Engine: hub 이벤트(`PortfolioSnapshotUpdated`, `StressResultsUpdated`)를 트리거로 exit 신호 계산 후 `ExitSignalEmitted`.
- 대시보드/모니터링: 최신 스냅샷 뷰를 읽어 리스크 상태를 시각화.

---

## 5. 장애/운영 가드

- 신선도: `as_of` 지연 상한(예: 5m) 초과 시 보수적 fallback(기본 상관 0.5, 이전 버전 스냅샷).
- 리트라이/알람: 이벤트 처리 실패 시 재시도 + 알림(Prometheus/Sentry).
- TTL: `ttl_sec` 만료 시 경고/폐기 처리.

---

## 6. 단계별 도입 계획 (초안)

1. **스냅샷 저장소 + 조회 API**: gateway가 스냅샷을 기록, WS/exit 엔진이 수동 조회.
2. **이벤트 발행/구독**: ControlBus/Kafka에 이벤트 발행, WS/exit 엔진 워커가 구독하여 자동 갱신/트리거.
3. **리스크/exit 신호 통합**: Exit Engine이 hub 이벤트를 기반으로 신호를 발행, WS/gateway가 적용/검증 경로를 통합.

---

## 7. 보완 작업(구현 계획)

- **스키마/데이터 계약**
  - 필수 필드 검증: 가중치 합≈1, `as_of` 지연 한도, `ttl_sec` 만료 처리.
  - 대용량 필드 분리: 공분산/실현 리턴은 inline 대신 `ref`(+hash/version)로 저장, 스냅샷에는 요약/참조만 포함.
  - Idempotency: `(world_id, version)` 충돌 정책 정의(덮어쓰기 vs 거절), hash 검증.
- **영속·캐시 계층**
  - Postgres/SQLite 인덱스(as_of, world_id) 및 최신/히스토리 조회 최적화.
  - Redis 캐시 또는 materialized view로 핫월드 지연 최소화.
  - 백필 스크립트: 기존 결정/포지션에서 초기 스냅샷 생성.
- **생산자 경로**
  - Rebalance 외 체결/포지션 싱크/alloc 스냅샷 후에도 hub push, 실패 시 재시도·DLQ.
  - ControlBus 토픽/키/재시도 설정 표준화(`risk_snapshot_updated`), gateway 쓰기 ACL(토큰/네트워크).
- **소비자 경로**
  - WS: ControlBus/큐 구독 워커 → 스냅샷 이벤트를 받아 ExtendedValidation/스트레스/라이브 워커 트리거(idempotent 실행 포함).
  - Exit 엔진: 이벤트 구독 후 추가 exit 신호 산출, 신호 스키마 정의.
  - 큐/스케줄러 표준화: Celery/Arq/ControlBus 핸들러 공통 모듈, 중복 방지.
- **운영/가시성**
- 모니터링: 최신 스냅샷 `as_of` 지연, 결측률, 이벤트 실패/재시도 메트릭, 알람.
- 감사/보안: actor/source/reason/cov_ref 서명/감사 로그, 민감 필드 마스킹 정책.
- 장애 대응: fail-closed 정책(스냅샷 오래되면 보수적 상관/σ), 재시도/백오프, DLQ 소비기.
- **테스트/문서**
- e2e: gateway→hub→ControlBus→WS 워커 경로, TTL/지연/손상 스냅샷 시나리오, 공분산 없는 fallback.
- 부하 테스트: 다수 전략/스냅샷에서 조회/캐시 hit 비율 확인.
- 운영 문서: 토픽/큐 설정, 권한 모델, 스키마/TTL 정책, runbook.

### 7.1 현재 코드 상태 대비 잔여 갭
- 구현됨: 필수 검증/TTL/hash, Redis 캐시 최신 조회, Postgres 인덱스, blob-store(offload/ref) 지원, ControlBus 이벤트 소비/발행, bearer token 보호, gateway push 재시도/backoff.
- 미구현/남은 것:
  - 대용량 ref 업로드/다운로드 헬퍼(프로듀서 공통)와 운영 수명/GC 정책(최소 TTL 정렬, pin/retention 옵션은 v1.5+).
  - 생산자 전면 적용: 체결/포지션 싱크·alloc 스냅샷 push + 재시도/ACL 일관화(리밸런스/activation 경로는 완료).
  - 운영 모니터링/알람: Prometheus 규칙 추가(`alert_rules.yml`에 RiskHubSnapshotStale/Missing), 런북 완성(`operations/risk_signal_hub_runbook.md`), metrics 노출(`risk_hub_snapshot_lag_seconds`, `risk_hub_snapshot_missing_total`), 헬스 스크립트(`scripts/risk_hub_monitor.py`).
  - 큐/ControlBus 워커 배포 예시와 idempotency 키: 미니멀 워커(`scripts/risk_hub_worker.py`) 제공, Celery/Arq 예시와 키 규칙은 운영 환경에 맞춰 확정 필요.
  - e2e/부하 테스트 시나리오 구현, CI 포함 여부 결정.

운영 런북: [operations/risk_signal_hub_runbook.md](../operations/risk_signal_hub_runbook.md) 참고.

---

## 8. 남은 결정/오픈 이슈

- 공분산/상관 추정 소스와 해상도(자산 vs 전략) 확정.
- 대용량 리턴/공분산의 ref 포맷(s3/redis/DB) 및 수명 관리.
- exit 신호 우선순위/override 정책(운영 문서와 정렬).
- 스냅샷 해시/서명 적용 여부(감사 요구 수준에 따라).

### 8.1 모니터링/알람 지표 (v1.5)
- `risk_hub_snapshot_dedupe_total{world_id,stage}`: dedupe 키 충돌로 스킵된 건수
- `risk_hub_snapshot_expired_total{world_id,stage}`: TTL 만료로 거부된 건수
- `risk_hub_snapshot_lag_seconds`(추가 예정): 최신 스냅샷 `as_of` 지연
- Alert 예시: dedupe/expired 급증, lag 초과 시 경고 → runbook으로 재처리/프로듀서 점검

## 9. 환경 구성(dev/prod 템플릿)

- `qmtl.yml`에 `risk_hub` 블록을 추가해 gateway/WS가 동일 설정을 공유한다.  
  `token`은 WS `risk_hub` 라우터 bearer 검증과 gateway `RiskHubClient` 양쪽에 주입된다.  
  `inline_cov_threshold`/`blob_store.inline_cov_threshold`는 hub와 gateway가 동일 기준으로 공분산을 offload/ref 처리하도록 맞춘다.
- Dev 템플릿(경량, fakeredis/인메모리 전용):
  ```yaml
  risk_hub:
    token: dev-hub-token           # 선택
    stage: paper                   # 기본 stage 헤더 (선택, 미지정 시 컨슈머 dedupe/알람이 unknown 라벨)
    inline_cov_threshold: 100      # dev는 공분산 inline 기본, offload 비활성
  ```
  - WS: in-memory/SQLite 메타 저장, 캐시/오프로드는 fakeredis(또는 순수 인메모리)만 사용한다. 별도 파일/S3 영속 스토리지는 dev에서 사용하지 않는다.
  - Gateway: 동일 토큰/threshold로 hub에 push. dev에서는 fakeredis 캐시/참조만 사용하고, 재시작 시 스냅샷이 사라져도 문제없는 최소 검증 흐름을 전제로 한다.
- Prod 템플릿(정식):
  ```yaml
  risk_hub:
    token: ${HUB_TOKEN}             # 필수, gateway에만 공유
    stage: live                     # 기본 stage 헤더 (backtest/paper/live 등)
    inline_cov_threshold: 50        # 큰 공분산은 ref로 강제
    blob_store:
      type: s3                      # 또는 redis
      bucket: qmtl-risk-snapshots
      prefix: risk/portfolios/
      inline_cov_threshold: 100
      cache_ttl: 900                # redis blob일 때 TTL
      redis_prefix: "risk-blobs:"
  ```
  - WS: Postgres `risk_snapshots` 테이블 + Redis 캐시, blob은 S3/OBS/GCS(또는 redis)로 offload.
  - Gateway: 동일 blob 스토어/threshold로 스냅샷을 push, WS는 `risk_hub.token`으로 보호.
  - dev/prod 전역 프로파일과 일관: 다른 모듈(WS/gateway/dagmanager/controlbus)과 동일 qmtl.yml을 사용하므로 환경 전환 시 hub 설정도 함께 적용된다.

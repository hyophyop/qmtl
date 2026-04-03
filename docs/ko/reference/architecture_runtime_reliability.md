---
title: "아키텍처 런타임 신뢰성"
tags: [reference, architecture, reliability]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 아키텍처 런타임 신뢰성

본 문서는 [QMTL 규범 아키텍처](../architecture/architecture.md)에서 분리한 운영 신뢰성, determinism 체크리스트, 보조 지침을 모아 둡니다. 서비스 경계와 SSOT 규칙은 아키텍처 문서가 규범이며, 이 문서는 그 규범을 운영 자산으로 옮길 때 점검해야 할 항목을 정리합니다.

## 1. 운영 신뢰성 제안 요약

1. **단일 실행 보장(Once-and-Only-Once)**  
   NodeID와 시간 버킷을 파티션 키로 삼아 Kafka 파티션과 lease 기반 오너십을 부여하고, 트랜잭셔널 커밋 로그로 중복 산출물을 제거합니다.
2. **이벤트-타임 워터마크와 지연 허용**  
   NodeCache가 워터마크를 유지하며 허용 지연 이내의 역행 데이터는 재계산하고, 초과 데이터는 정책에 따라 무시하거나 별도 처리합니다.
3. **런타임 지문(runtime fingerprint)**  
   Python, NumPy 등 런타임 버전을 fingerprint로 기록하고, `runtime_compat` 정책에 따라 재사용 여부를 결정합니다.
4. **스냅샷 상태 하이드레이션**  
   NodeCache를 주기적으로 Arrow/Parquet 스냅샷으로 저장해 재기동 시 하이드레이션함으로써 웜업 시간을 줄입니다.
5. **Schema Registry 및 CloudEvents 사용**  
   데이터 토픽은 Avro/Proto + Schema Registry, 제어 토픽은 CloudEvents over Protobuf 기준으로 정렬합니다.

## 2. Determinism 체크리스트

아래 항목은 전역 DAG 일관성과 고신뢰 큐 오케스트레이션을 검증할 때 기준으로 사용합니다.

1. **Gateway ↔ SDK CRC 검증**  
   Gateway가 계산한 `node_id`와 SDK가 사전 계산한 값이 `crc32` 필드로 상호 검증되는지 확인합니다.
2. **NodeCache 가드레일 & GC**  
   `period × interval` 초과 슬라이스가 즉시 evict되고 Arrow chunk zero-copy 전달이 유지되는지 확인합니다.
3. **Kafka Topic Create 재시도**  
   `CREATE_TOPICS → VERIFY → WAIT → BACKOFF` 루프와 broker metadata 검증으로 근접 이름 충돌을 제거합니다.
4. **Sentinel Traffic Shift 확인**  
   `traffic_weight` 변경 시 Gateway와 SDK가 5초 이내 동기화되는지 확인합니다.
5. **TagQueryNode 동적 확장**  
   Gateway가 새 `(tags, interval)` 큐를 발견하면 `tagquery.upsert`를 발행하고 Runner가 버퍼를 자동 초기화하는지 확인합니다.
6. **Minor-schema 버퍼링**  
   `schema_minor_change`는 재사용하되 7일 후 자동 full-recompute가 실행되도록 유지합니다.
7. **GSG Canonicalize & SSA DAG Lint**  
   DAG를 canonical JSON + SSA로 변환해 NodeID 재계산이 일치하는지 검증합니다.
8. **Golden-Signal SLO/Alert**  
   `diff_duration_ms_p95`, `nodecache_resident_bytes`, `sentinel_gap_count`와 submit→activation 골든 시그널을 지속 관측합니다.
9. **극단 장애 플레이북**  
   Neo4j 전체 장애, Kafka 메타데이터 손상, Redis AOF 손실 시나리오별 runbook과 대시보드를 교차 링크합니다.
10. **4단계 CI/CD Gate**  
    SSA lint, 빠른 백테스트, 24h 카나리아, 50% 프로모션, 한 줄 롤백으로 이어지는 게이트를 검증합니다.
11. **NodeID 월드 배제 확인**  
    `world_id`가 NodeID 입력에 포함되지 않는지 정적/동적으로 검증합니다.
12. **TagQueryNode 안정성 검사**  
    신규 큐 발견 전후에도 `query_tags`/`match_mode`/`interval`이 같으면 NodeID가 변하지 않는지 확인합니다.

## 3. 관측 및 런북 연결

- Gateway 메트릭:
  - `nodeid_checksum_mismatch_total{source="dag"}`
  - `nodeid_missing_fields_total{field,node_type}`
  - `nodeid_mismatch_total{node_type}`
  - `tagquery_nodeid_mismatch_total`
- 운영 런북:
  - [Determinism Runbook](../operations/determinism.md)
  - [Core Loop Golden Signals](../operations/core_loop_golden_signals.md)
  - [ControlBus 운영](../operations/controlbus_operations.md)

NodeID CRC 또는 TagQuery 불일치가 상승하면 DAG 재생성과 Core Loop 계약 테스트(`tests/e2e/core_loop`)를 함께 실행해 복구를 검증해야 합니다.

## 4. 추가 지침

- 프로모션 정책과 EvalKey는 항상 `dataset_fingerprint`를 고정해야 하며, 누락 시 apply는 강등 또는 거부되어야 합니다.
- `observability.slo.cross_context_cache_hit`는 항상 0을 유지해야 하며, 위반 시 원인 제거 전까지 실행을 멈춥니다.
- 정책 번들은 `share_policy`, edge override, 리스크 한도를 명시해 감사 가능성을 유지해야 합니다.
- 전략 스캐폴드 변경은 공개 `qmtl init` 경로와 전략 워크플로 문서에 맞춰 동기화해야 합니다.

{{ nav_links() }}

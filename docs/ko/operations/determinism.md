---
title: "Determinism 런북 — NodeID/TagQuery 불일치 대응"
tags: [operations, determinism, runbook]
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# Determinism 런북 — NodeID/TagQuery 불일치 대응

## 모니터링 포인트
- Gateway 메트릭
  - `nodeid_checksum_mismatch_total{source="dag"}`: 제출된 `node_ids_crc32`가 재계산 값과 불일치
  - `nodeid_missing_fields_total{field,node_type}`: canonical NodeID 입력 필드 누락
  - `nodeid_mismatch_total{node_type}`: 제출된 `node_id`가 `compute_node_id`와 다름
  - `tagquery_nodeid_mismatch_total`: TagQueryNode 전용 불일치 카운터
  - `worlds_compute_context_downgrade_total{reason}`, `strategy_compute_context_downgrade_total{reason}`: WS 결정 부재/만료/`as_of` 누락 시 default-safe 강등이 제대로 걸리는지 확인
- SDK 메트릭
  - `tagquery_update_total{outcome,reason}`: TagQuery 큐 업데이트 이벤트의 처리 결과(`applied`/`deduped`/`unmatched`/`dropped` = `missing_interval|missing_tags|invalid_spec`) 분포
  - `nodecache_resident_bytes{node_id}`: DAG Manager/SDK NodeCache GC가 동작하는지(작업 후 감소/안정) 확인
- 경보 발생 시 직전 제출/큐맵을 덤프해 재현 가능한 DAG 스냅샷을 확보한다.

## 즉시 대응 절차
1) **CRC 불일치 (`nodeid_checksum_mismatch_total`)**
   - DAG JSON을 풀어 `node_ids_crc32`를 로컬에서 재계산한다(`qmtl.foundation.common.crc32_of_list`).
   - SDK가 생성한 node_id와 Gateway 재계산 값이 같은지 확인 후 CRC를 재생성해 제출한다.

2) **필수 필드 누락 (`nodeid_missing_fields_total`)**
   - 누락된 필드를 로그/메트릭에서 확인 후 SDK를 최신 버전으로 재생성한다.
   - `code_hash/config_hash/schema_hash/schema_compat_id`가 모두 채워졌는지 검증한다. TagQueryNode는 `interval`과 최소 한 개의 `tag`가 없으면 결정성 검증을 통과하지 않는다.

3) **NodeID 불일치 (`nodeid_mismatch_total`)**
   - `compute_node_id`로 재계산해 제출된 값과 비교한다.
   - TagQueryNode인 경우 `query_tags` 정렬/중복 제거, `match_mode`, `interval`이 모두 params에 포함됐는지 확인하고 재계산한다.

4) **TagQuery 업데이트 드롭 (`tagquery_update_total{outcome=\"dropped\"|\"unmatched\"}`)**
   - `missing_interval|missing_tags`: WS/DAG가 내보내는 TagQuery payload에 정규화된 tag와 interval이 포함되도록 재생성한다.
   - `no_registered_node`: DAG와 SDK 등록된 TagQueryNode 사양이 어긋난 상태이므로 NodeID 정규화 혹은 match_mode/interval 불일치를 점검한다.
5) **ComputeContext 강등 스파이크 (`worlds_compute_context_downgrade_total`/`strategy_compute_context_downgrade_total`)**
   - WS `decide`/`activation` 응답이 늦거나 누락되었는지 확인하고, WS health/TTL을 점검한다.
   - 클라이언트 제출 메타에 `as_of`/`dataset_fingerprint`가 누락되지 않았는지 확인한다. 누락된 경우 compute-only 강등은 정상이며, 런북/계약 테스트의 기본 동작이다.
   - WS 응답이 stale(ETag/TTL 만료)로 표시되는 경우, WS 캐시/프록시/연결 문제를 우선 점검하고 필요 시 WS를 재시작한다.

6) **NodeCache GC/메모리 누적 (`nodecache_resident_bytes`)**
   - 단조 증가하거나 GC 이후에도 감소하지 않으면 NodeCache가 오래된 노드를 보존 중일 수 있다. DAG Manager/SDK 프로세스 재시작으로 캐시를 비우고, NodeID CRC 불일치가 없는지 함께 확인한다.
   - GC 후에도 반복 증가하면 NodeID 계산 규칙이 자주 변경되고 있을 가능성이 있으니, NodeID 결정성 규칙 문서와 계약 테스트(`tests/e2e/core_loop`)를 확인해 규칙을 재고정한다.

## 복구 검증
- 수정한 DAG로 재제출 후 메트릭 증가가 멈추는지 확인한다.
- Core Loop 계약 테스트를 실행해 회귀가 없는지 확인:

```bash
CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q
```

## 참고
- 설계 근거: `docs/ko/architecture/architecture.md` §6 Deterministic Checklist.
- 세계/도메인 격리 검증: `tests/e2e/test_world_isolation.py`.
- 대시보드: `nodeid_checksum_mismatch_total`, `nodeid_missing_fields_total`, `nodeid_mismatch_total`, `tagquery_nodeid_mismatch_total`, `tagquery_update_total`, `worlds_compute_context_downgrade_total`, `nodecache_resident_bytes`를 함께 시각화해 결정성 드리프트와 강등/GC 문제를 감시한다.

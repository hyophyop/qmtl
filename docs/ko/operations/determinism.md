---
title: "Determinism 런북 — NodeID/TagQuery 불일치 대응"
tags: [operations, determinism, runbook]
author: "QMTL Team"
last_modified: 2025-09-01
---

{{ nav_links() }}

# Determinism 런북 — NodeID/TagQuery 불일치 대응

## 모니터링 포인트
- Gateway 메트릭
  - `nodeid_checksum_mismatch_total{source="dag"}`: 제출된 `node_ids_crc32`가 재계산 값과 불일치
  - `nodeid_missing_fields_total{field,node_type}`: canonical NodeID 입력 필드 누락
  - `nodeid_mismatch_total{node_type}`: 제출된 `node_id`가 `compute_node_id`와 다름
  - `tagquery_nodeid_mismatch_total`: TagQueryNode 전용 불일치 카운터
- SDK 메트릭
  - `tagquery_update_total{outcome,reason}`: TagQuery 큐 업데이트 이벤트의 처리 결과(`applied`/`deduped`/`unmatched`/`dropped` = `missing_interval|missing_tags|invalid_spec`) 분포
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

## 복구 검증
- 수정한 DAG로 재제출 후 메트릭 증가가 멈추는지 확인한다.
- Core Loop 계약 테스트를 실행해 회귀가 없는지 확인:

```bash
CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q
```

## 참고
- 설계 근거: `docs/ko/architecture/architecture.md` §6 Deterministic Checklist.
- 세계/도메인 격리 검증: `tests/e2e/test_world_isolation.py`.
- 대시보드: `nodeid_checksum_mismatch_total`, `nodeid_missing_fields_total`, `nodeid_mismatch_total`, `tagquery_nodeid_mismatch_total`, `tagquery_update_total` 지표를 함께 시각화해 결정성 드리프트와 큐 업데이트 드롭률을 감시한다.

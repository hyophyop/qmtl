---
title: "마이그레이션: BLAKE3 NodeID"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-07
---

{{ nav_links() }}

# 마이그레이션: BLAKE3 NodeID

NodeID 알고리즘은 `blake3:` 접두사가 필수인 BLAKE3를 사용하며 `world_id`를 포함해선 안 됩니다. 레거시 SHA 기반 ID는 더 이상 허용되지 않으며 관련 헬퍼도 제거되었습니다.

## 변경 사항

- `compute_node_id`는 정규 노드 명세로부터 계산한 `blake3:<digest>`를 반환합니다:
  `(node_type, interval, period, params(정규 JSON), dependencies(정렬), schema_compat_id, code_hash)`
  `schema_hash`와 `config_hash`는 검증을 위한 페이로드 필드로 유지되지만, 더 이상 다이제스트 입력이 아닙니다.
- 레거시 헬퍼 `compute_legacy_node_id`는 제거되었으며, Gateway는 비정규 ID를 거부합니다.

## 수행 항목

- 모든 코드 경로에서 `compute_node_id`만 사용하도록 변경하세요.
- 저장된 NodeID는 정규 `blake3:` 형식으로 마이그레이션하세요.
- 코드베이스의 `compute_legacy_node_id` 참조를 제거하세요.
- DAG 직렬화 시 `schema_compat_id`, 정규화된 `params`(또는 `config`) 값, 정렬된 의존성 목록을 포함해 Gateway 검증이 정규 ID를 재계산할 수 있게 하세요.
- 호환성 점검을 위해 `code_hash`, `config_hash`, `schema_hash`는 계속 전송하세요. Gateway는 `schema_compat_id` 외에도 이들의 존재를 검증합니다.

{{ nav_links() }}

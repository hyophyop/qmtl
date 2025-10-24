# 노드 식별 검증

`qmtl.foundation.common.node_validation` 모듈은 Gateway 인입, CLI 도구, SDK 드라이런 경로에서 사용하는 체크섬 및 필드 검사를 중앙 집중화합니다. 헬퍼는 표준 [`compute_node_id`](../architecture/gateway.md) 루틴을 감싸 모든 진입점이 동일한 계약을 강제합니다.

## API 요약

- `validate_node_identity(nodes, provided_checksum)` 은 계산된 CRC32 체크섬, 누락 필드, 불일치 식별자를 포함하는 `NodeValidationReport` 를 반환합니다.
- `enforce_node_identity(nodes, provided_checksum)` 은 동일한 검증을 수행하지만 페이로드가 잘못되면 `NodeValidationError` 를 발생시킵니다.
- `NodeValidationReport.raise_for_issues()` 는 보고서에 기록된 문제를 `NodeValidationError` 로 승격해 진단 수집 후 예외를 던질 수 있게 합니다.
- `REQUIRED_NODE_FIELDS` 는 `node_type`, `code_hash`, `config_hash`, `schema_hash`, `schema_compat_id` 등 결정적 해싱에 필요한 필드 튜플을 노출합니다.

`NodeValidationError.detail` 페이로드는 `NodeIdentityValidator` 가 FastAPI를 통해 반환하던 응답과 동일한 구조를 유지해 REST 클라이언트 하위 호환성을 보장합니다.

## 오류 코드

| 코드 | 설명 |
| ---- | ----- |
| `E_NODE_ID_FIELDS` | 필수 속성 중 하나 이상이 누락되었습니다. 오류 페이로드에는 `missing_fields` 목록과 수정 힌트가 포함됩니다. |
| `E_CHECKSUM_MISMATCH` | 제공된 CRC32 체크섬이 제출된 노드 식별자로 계산한 값과 일치하지 않습니다. |
| `E_NODE_ID_MISMATCH` | 하나 이상의 노드 `node_id` 가 표준 `compute_node_id` 결과와 다릅니다. 오류 페이로드는 불일치 노드를 나열합니다. |

## 사용 예시

```python
from qmtl.foundation.common import crc32_of_list, enforce_node_identity

def validate_payload(dag: dict[str, object], checksum: int) -> None:
    nodes = dag.get("nodes", [])
    enforce_node_identity(nodes, checksum)

dag = {"nodes": [some_node]}
checksum = crc32_of_list([node["node_id"] for node in dag["nodes"]])
validate_payload(dag, checksum)
```

Gateway 제출 파이프라인과 CLI는 이제 이 모듈을 공유해 모든 소비자가 일관된 진단과 힌트 텍스트를 받을 수 있습니다.

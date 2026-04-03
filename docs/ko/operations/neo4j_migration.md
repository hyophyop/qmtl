# Neo4j 스키마 초기화

이 가이드는 DAG Manager의 Neo4j 스키마 초기화 작업을 어떻게 실행하고 재실행하는지 설명한다.

- 명령: `qmtl --admin dagmanager-server neo4j-init`
- 동작: idempotent, 언제든 안전하게 재실행 가능
- 범위: 고트래픽 질의에 필요한 제약 조건과 인덱스를 생성

## 생성되는 항목

초기화기는 아직 존재하지 않는 경우에만 다음 작업을 적용한다.

- Compute node primary key: `(:ComputeNode {node_id})` 유니크 제약
- Queue topic index: `(:Queue {topic})` 인덱스
- Queue interval index: `(:Queue {interval})` 인덱스
- Compute tags index: `(:ComputeNode {tags})` 인덱스
- Buffering sweep index: `(:ComputeNode {buffering_since})` 인덱스

이들은 다음 빠른 경로를 지원한다.

- `node_id` 기반 노드 조회와 topic-bound 라우팅
- interval 필터를 포함한 tag → queue 해상도
- buffering 노드 주기 스윕

## 사용법

```bash
qmtl --admin dagmanager-server neo4j-init \
  --uri bolt://localhost:7687 \
  --user neo4j \
  --password neo4j
```

- `CREATE … IF NOT EXISTS`를 사용하므로 재실행해도 안전하다.
- 스키마 메타데이터 외의 데이터는 수정하지 않는다.

## 성능 메모

추가되는 인덱스는 DAG Manager의 대표 질의를 기준으로 선택되었다. 중간 규모 그래프에서는 이 인덱스들이 p95 질의 지연을 목표 범위 안에 유지하도록 돕는다. 워크로드가 크게 다르다면(예: 추가 label/property 필터 사용) 같은 패턴으로 전용 인덱스를 추가하는 것을 고려한다.

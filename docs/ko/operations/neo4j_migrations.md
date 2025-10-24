# Neo4j 마이그레이션 & 롤백

이 문서는 DAG Manager의 Neo4j 스키마를 초기화, 점검, 롤백하는 방법을 설명합니다.

## 초기화(idempotent)

모든 DDL은 `IF NOT EXISTS` 를 사용하므로 재실행해도 안전합니다.

```
qmtl service dagmanager neo4j-init \
  --uri bolt://localhost:7687 --user neo4j --password neo4j
```

## 현재 스키마 내보내기

```
qmtl service dagmanager export-schema \
  --uri bolt://localhost:7687 --user neo4j --password neo4j --out schema.cypher
```

## 롤백(생성된 객체 삭제)

`neo4j-init` 가 만든 제약 조건과 인덱스를 `DROP ... IF EXISTS` 로 제거합니다.

```
qmtl service dagmanager neo4j-rollback \
  --uri bolt://localhost:7687 --user neo4j --password neo4j
```

하위 환경에서 주의 깊게 사용하세요. 프로덕션 롤백은 통제된 마이그레이션 계획을 따라야 합니다.

## WorldNodeRef 도메인 확장(백테스트/드라이런/라이브 분리)

### 목표

- `WorldNodeRef` 복합 키에 `execution_domain` 을 일급 구성 요소로 승격합니다.
- 기존 리더를 방해하지 않고 `(world_id, node_id)` 당 다중 도메인 스코프 레코드를 허용합니다.

### 무중단 접근 방식

1. **호환 가능한 코드 배포**
   - Gateway와 WorldService 노드가 다중 도메인 버킷을 이해하는 릴리스를 실행 중인지 확인합니다. 메모리 `Storage` 레이어는 기존 페이로드를 자동으로 정규화하고 알 수 없는 도메인은 `live` 로 기본 설정합니다.
2. **Neo4j 제약 조건 추가/업데이트**
   - `CREATE CONSTRAINT world_node_ref_key IF NOT EXISTS FOR (w:WorldNodeRef) REQUIRE (w.world_id, w.node_id, w.execution_domain) IS UNIQUE;`
   - 기존 단일 도메인 유니크 제약은 롤아웃 동안 유지할 수 있으며, 백필 완료 후 제거하세요.
3. **백필 / 지연 마이그레이션**
   - _지연 경로_: 트래픽이 기존 노드를 읽도록 허용하면 서비스가 `execution_domain` 이 없는 레거시 레코드를 읽을 때 `live` 로 변환합니다.
   - _백필 경로_: Cypher 작업으로 각 `WorldNodeRef` 를 명시적 도메인 버킷으로 복제합니다.
     ```cypher
     MATCH (n:WorldNodeRef)
     WHERE n.execution_domain IS NULL OR n.execution_domain = ""
     SET n.execution_domain = "live";
     ```
   - 사전 채움된 `backtest`/`dryrun` 버킷이 필요한 월드는 도메인별 Gateway "world node upsert" 작업을 재생하세요.
4. **검증**
   - `MATCH (n:WorldNodeRef) RETURN n.execution_domain, count(*) ORDER BY n.execution_domain;` 로 히스토그램이 기대와 일치하는지 샘플링합니다.
   - 자동화 커버리지: `tests/qmtl/services/worldservice/test_worldservice_api.py::test_world_nodes_execution_domains_and_legacy_migration` 이 공용 API를 통해 지연 변환 경로를 검증합니다.
   - WorldService는 레거시 페이로드가 온디맨드 승격될 때 `world_node_bucket_normalized` 감사를 남깁니다. `GET /worlds/{id}/audit` 로 수동 개입 없이 완료되는지 모니터링하세요.

### 롤백

- Neo4j 롤백은 `DROP CONSTRAINT world_node_ref_key IF EXISTS;` 후 이전 스냅샷 복원으로 충분합니다.
- 애플리케이션은 `execution_domain` 누락을 허용하므로 롤백은 메타데이터 변경일 뿐이며 데이터는 계속 유효합니다.

## EvalKey 재계산 계획

### 목표

- 검증 캐시 키에 `execution_domain` 을 포함해 엄격한 분리를 보장합니다.
- 도메인 구성요소 없이 해시된 레거시 항목을 만료시킵니다.

### 전략

1. **호환 서비스 배포** – 새 튜플 `(node_id, world_id, execution_domain, contract_id, dataset_fingerprint, code_version, resource_policy)` 로 EvalKey를 재계산합니다.
2. **지연 무효화**
   - 조회 시 컨텍스트를 재해시하고 키가 일치하지 않으면 버린 뒤 재검증합니다.
   - 테스트 커버리지는 `tests/qmtl/services/worldservice/test_validation_cache.py::test_validation_cache_legacy_payloads_are_normalised_and_invalidated` 가 담당합니다.
   - 표준화된 실행 도메인은 `tests/qmtl/services/worldservice/test_validation_cache.py::test_validation_cache_normalises_execution_domain_on_set` 로 검증돼 롤아웃 동안 캐시 버킷이 분기되지 않도록 합니다.
   - 감사 로그는 페이로드가 다시 작성될 때 `validation_cache_bucket_normalized`, 오래된 EvalKey를 제거하면 `validation_cache_invalidated` 이벤트를 남겨 운영 추적을 제공합니다.
3. **선제적 정리(선택)**
   - `MATCH (v:Validation) REMOVE v.eval_key_without_domain;`
   - 즉시 재검증을 강제하려면 `MATCH (v:Validation) WHERE v.version < $cutover REMOVE v` 와 같이 `Validation` 노드를 삭제합니다(스키마에 맞게 조건 조정).

### 검증

- 검증 캐시 미스 메트릭을 모니터링하세요. 롤아웃 동안 스파이크가 예상되며 캐시가 다시 채워지면 안정화돼야 합니다.
- Neo4j 스냅샷에서 새 항목이 `execution_domain` 필드를 포함하는지 확인하세요.

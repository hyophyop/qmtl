# DAG Manager 컴퓨트 컨텍스트 롤아웃

2025년 9월 릴리스에서는 `DiffRequest` 를 통해 컴퓨트 컨텍스트가 전파되고, 도메인 범위 컴퓨트 키가 `queue_map` 키에 솔트로 추가됩니다. 이 문서는 호환성 확보에 필요한 단계와 권장 롤링 배포 순서를 정리합니다.

## 요약

- `DiffService.DiffRequest` 는 `world_id`, `execution_domain`, `as_of`, `partition`, `dataset_fingerprint` 필드를 선택적으로 받습니다.
- Gateway, DAG Manager, SDK는 `qmtl/foundation/common/compute_context.py` 에 구현된 표준 컴퓨트 컨텍스트 모델을 공유합니다. Gateway는 이를 `StrategyComputeContext` 로 감싸 다운그레이드 메타데이터, Redis 매핑, 커밋 로그 페이로드를 서비스 간 일치시키므로, 모든 서비스를 동시에 업그레이드해야 호환성을 유지할 수 있습니다.
- `DiffService` 는 도메인 범위 컴퓨트 키를 계산해 각 `queue_map` 파티션 키에 `...#ck=<hash>` 형식으로 추가합니다. 다운스트림 소비자는 `node_id` 를 추출하기 전에 `#ck=` 접미사를 제거해야 합니다.
- 프로토콜 마이너 버전을 높인 뒤 gRPC 스텁을 다시 생성하세요(예: `dagmanager.proto` v1.4 → v1.5). 이 변경을 반영한 Python 배포본(Gateway, DAG Manager 패키지)의 마이너 버전도 함께 올리는 것이 좋습니다.

## 롤링 배포 계획

1. **아티팩트 준비**
   - gRPC 스텁 재생성(`uv run python -m grpc_tools.protoc ...`).
   - 다음을 충족하는 Gateway 빌드 배포:
     - 새 컴퓨트 컨텍스트 필드를 발견하면 전달.
     - `#ck=` 가 포함된 `queue_map` 키를 안전하게 파싱.
   - 새 필드를 이해하고 컴퓨트 키를 도출하는 DAG Manager 빌드 배포.

2. **Gateway 우선 업그레이드**
   - 모든 리전에 새 Gateway 릴리스를 순차 배포합니다. 새 클라이언트는 기존 DAG Manager와 호환되므로(접미사가 없는 키도 정상 파싱) 문제 없습니다.
   - Gateway 헬스 엔드포인트와 `dagclient_breaker_state`, `dagclient_breaker_failures` 메트릭을 확인하세요.

3. **DAG Manager 업그레이드**
   - DAG Manager 인스턴스를 한 번에 하나씩 드레인하고 새 버전으로 롤 포워드합니다. 카나리부터 시작해 다음을 관찰하세요.
     - `dagmanager_diff_failures_total`
     - `dagmanager_queue_create_error_total`
     - Gateway 인입 성공 지표
   - 안정이 확인되면 나머지 풀에 배포를 확장합니다.

4. **배포 후 검증**
   - `queue_map` 응답에 `#ck=` 접미사가 포함되는지, Gateway 워커가 계속 전략을 처리하는지 확인합니다.
   - TagQuery 조회와 WebSocket 큐 맵 브로드캐스트에서 새 형식이 정상 동작하는지 점검합니다.

## 롤백 고려 사항

- DAG Manager 업그레이드 이후 문제가 발생하면 Gateway 릴리스는 유지한 채 DAG Manager만 롤백하세요. Gateway는 기존 `queue_map` 형식을 그대로 처리합니다.
- Gateway 롤백이 필요하다면 Gateway를 먼저 되돌린 뒤 DAG Manager를 이전 빌드로 낮출지 평가하세요.

배포 순서를 Gateway → DAG Manager로 유지하면 `#ck=` 접미사를 해석할 수 없는 클라이언트가 새 키를 보는 상황을 예방할 수 있습니다.

# QMTL 차세대 구조 설계 제안 및 논의

## 프로젝트 디렉토리 및 개발 환경 표준

- src/qmtl/ 하위에 모든 서비스/공통 모듈/모델/도메인 계층을 구성한다.
- pyproject.toml로 의존성 및 빌드/테스트/포맷팅 도구를 관리한다(uv 사용 권장).
- Makefile로 lint, test, build, run, docker 등 개발 명령을 표준화한다.
- .gitignore, .editorconfig로 코드 스타일과 불필요 파일을 관리한다.
- tests/ 하위에 unit, integration, e2e 계층별 테스트 디렉토리를 분리한다.

## 테스트 프레임워크 및 컨테이너 관리 전략
- tests/unit, tests/integration, tests/e2e 계층별 디렉토리 분리
- tests/conftest.py에서 pytest fixture로 docker-compose 컨테이너를 자동 기동/정리(포트 충돌 방지)
- E2E 테스트는 서비스 기동 대기(health check, 최대 30초 재시도) 후 워크플로우 검증
- 모든 API 엔드포인트 및 주요 비즈니스 로직에 대한 테스트 필수, 커버리지 80% 이상 목표
- Makefile test, integration-test, e2e-test, coverage 명령으로 테스트 일관성 보장

## 0. 요약

QMTL 시스템을 3개의 독립적인 서비스로 분리하여 관심사 분리(SoC), 확장성, 운영 효율성을 극대화합니다:

1. **QMTL DAG Manager**: 글로벌 DAG와 메시지 브로커 스트림 통합 관리
2. **QMTL Gateway**: DAG Manager와 SDK 사이의 조율 및 작업 큐 관리
3. **QMTL SDK**: 사용자 전략 작성/실행 및 DAG 추출

이 문서는 개발/리팩토링에 직접 활용 가능한 상세 설계와 구현 가이드를 제공합니다.

## 1. API 설계 원칙: protobuf contract 기반 조회 전용
- **protobuf contract(스키마) 기반 모델은 외부 API에서 조회(read)만 허용, 직접 조작(mutate)은 불가**
  - 모든 서비스(API)는 protobuf 기반 데이터 구조를 조회(검색, 상세, 목록 등)하는 엔드포인트만 제공
  - 데이터 생성/수정/삭제 등 조작은 내부 서비스 로직(비즈니스 계층, 서비스 간 RPC 등)에서만 수행, 외부 API 명세에는 아예 노출하지 않음
  - contract의 무결성, 관심사 분리, 데이터 일관성 보장
  - 예시: `/v1/dag-manager/nodes` GET(조회)만 외부에 공개, POST/PUT/DELETE 등은 내부 서비스에서만 사용

## 2. 컴포넌트별 역할 및 책임

### QMTL DAG Manager
- **글로벌 DAG(Directed Acyclic Graph) 관리의 단일 책임 서비스**
- **주요 구성요소**:
  - `NodeManager`: 노드 CRUD, 참조 카운트, 메타데이터 관리 (`Neo4jNodeManagementService`)
  - `StreamManager`: Kafka/Redpanda 토픽 생성/삭제/관리 (`KafkaTopicService`)
  - `DependencyManager`: 노드 간 의존성 관계 관리 (`Neo4jDependencyService`)
  - `MetadataService`: 노드/DAG 메타데이터 통합 관리 (파사드 패턴)
  - `EventPublisher`: 상태 변경 이벤트 발행 (`RedisEventPublisher`)

- **핵심 API 및 엔드포인트**:
  - `/v1/dag-manager/nodes`: 노드 조회 (GET만 외부에 공개)
  - `/v1/dag-manager/nodes/{node_id}/dependencies`: 의존성 조회 (GET)
  - `/v1/dag-manager/nodes/by-tags`: TAG 기반 노드 메타데이터 조회 (GET)
  - `/v1/dag-manager/streams`: 스트림(토픽) 조회 (GET)
  - `/v1/dag-manager/events`: 이벤트 구독/발행 (GET)
  - `/v1/dag-manager/nodes/{node_id}/callbacks`: 콜백 조회 (GET)
  - **노드 생성/수정/삭제 등 조작은 Gateway 등 내부 서비스에서만 호출 가능 (외부 API 명세에는 미노출)**

- **주요 구현 클래스/모듈**:
  - `src/qmtl/dag_manager/services/node_service.py`: 노드 관리 서비스
  - `src/qmtl/dag_manager/services/stream_service.py`: 스트림 관리 서비스 
  - `src/qmtl/dag_manager/repositories/neo4j_node_repository.py`: Neo4j 노드 저장소
  - `src/qmtl/dag_manager/repositories/kafka_topic_repository.py`: Kafka 토픽 저장소

- **주요 모델 및 인터페이스**:
  - `models/node.py`: 노드 정의 및 상태 모델 (protobuf 기반)
  - `models/dag.py`: DAG 구조 모델 (protobuf 기반)
  - `models/stream.py`: 스트림 메타데이터 모델 (protobuf 기반)
  - `models/event.py`: 이벤트 및 콜백 모델 (protobuf 기반)

### QMTL Gateway
- **SDK와 DAG Manager 사이의 중계 및 조율 서비스**
- **주요 구성요소**:
  - `WorkQueueManager`: 작업 큐 관리 및 처리 (`RedisWorkQueueService`)
  - `DagSyncService`: DAG Manager와 SDK 간 동기화 처리
  - `CallbackManager`: SDK에 대한 콜백/이벤트 처리
  - `StateTrackingService`: 전략 및 노드 상태 추적/제공
  - `QueryNodeResolver`: TAG 기반 QueryNode 메타데이터 해석/제공

- **핵심 API 및 엔드포인트**:
  - `/v1/gateway/strategies`: 전략 조회 (GET만 외부에 공개)
  - `/v1/gateway/strategies/{strategy_id}/status`: 전략 상태 조회 (GET)
  - `/v1/gateway/callbacks`: 콜백 조회 (GET)
  - `/v1/gateway/nodes`: 실행 가능한 노드 목록 조회 (GET)
  - `/v1/gateway/events`: 이벤트 구독/발행 (GET)
  - **전략 생성/수정/삭제 등 조작은 SDK→Gateway 내부 호출 및 Gateway→DAG Manager 내부 호출로만 동작 (외부 API 명세에는 미노출)**

- **주요 구현 클래스/모듈**:
  - `src/qmtl/gateway/services/work_queue_service.py`: 작업 큐 관리
  - `src/qmtl/gateway/services/callback_service.py`: 콜백 처리
  - `src/qmtl/gateway/services/dag_sync_service.py`: DAG 동기화
  - `src/qmtl/gateway/repositories/redis_queue_repository.py`: Redis 기반 큐 저장소
  - `src/qmtl/gateway/clients/dag_manager_client.py`: DAG Manager API 클라이언트

- **작업 큐 처리 절차**:
  1. `enqueue_work`: 전략 실행/종료 등 작업 큐에 등록 (내부 서비스 간 조작)
  2. `process_work`: 작업 처리(DAG Manager 메타데이터 조회, 큐 생성 요청 등)
  3. `handle_result`: 처리 결과 상태 업데이트 및 SDK 콜백
  4. `retry_failed_work`: 실패한 작업 재시도 처리

- **주요 모델 및 인터페이스**:
  - `models/work.py`: 작업 정의 및 상태 모델 (protobuf 기반)
  - `models/callback.py`: 콜백 및 이벤트 모델 (protobuf 기반)
  - `models/strategy.py`: 전략 및 요청 모델 (protobuf 기반)

### QMTL SDK
- **사용자 전략(DAG) 작성 및 실행의 표준 인터페이스**
- **주요 구성요소**:
  - `DagExtractor`: PyTorch 스타일 코드에서 DAG 구조 추출
  - `GatewayClient`: Gateway 서비스와의 통신 처리
  - `NodeExecutor`: 실행 가능한 노드만 선택적 실행
  - `CallbackHandler`: Gateway로부터 콜백/이벤트 수신 처리
  - `StateManager`: 노드/전략 상태 관리 및 저장

- **핵심 API 및 클래스**:
  - `Node`: 기본 노드 클래스(데코레이터 기반, protobuf 기반 모델 활용)
  - `SourceNode`: 데이터 소스 노드 (protobuf 기반)
  - `DataNode`: 데이터 처리 노드 (protobuf 기반)
  - `QueryNode`: 태그 기반 동적 참조 노드 (protobuf 기반)
  - `run_strategy()`: 전략 실행 및 DAG 추출
  - `get_node_status()`: 노드 상태 조회
  - `StreamSettings`: 스트림 설정 관리 (protobuf 기반)

- **주요 구현 클래스/모듈**:
  - `src/qmtl/sdk/core/dag_extractor.py`: DAG 추출 및 분석
  - `src/qmtl/sdk/core/node_executor.py`: 노드 실행 엔진
  - `src/qmtl/sdk/core/callback_handler.py`: 콜백 처리
  - `src/qmtl/sdk/clients/gateway_client.py`: Gateway API 클라이언트
  - `src/qmtl/sdk/utils/node_id_generator.py`: Node ID 생성

- **노드 정의 및 실행 예시**:
  ```python
  from qmtl.models.node import DataNode
  from qmtl.sdk import run_strategy

  @DataNode(stream_settings={"interval": "1m"})
  def process_data(data):
      return data * 2

  @DataNode(upstream=[process_data])
  def analyze_result(data):
      return data.mean()

  # 전략 실행 - DAG 추출 및 Gateway 제출
  if __name__ == "__main__":
      result = run_strategy()
      print(f"Strategy status: {result.status}")
  ```

- **주요 모델 및 인터페이스**:
  - `models/node.py`: 노드 정의 및 실행 모델 (protobuf 기반)
  - `models/stream_settings.py`: 스트림 설정 모델 (protobuf 기반)
  - `models/strategy_result.py`: 전략 실행 결과 모델 (protobuf 기반)


## 2. 전체 워크플로우 예시

### 2.1 기본 전략 실행 흐름

1. **전략 파일 실행 및 DAG 추출** (SDK):
   ```python
   # 사용자 전략 파일 (strategy.py)
   from qmtl.sdk import DataNode, run_strategy
   
   @DataNode(stream_settings={"interval": "1m"})
   def source():
       return {"data": [1, 2, 3]}
   
   @DataNode(upstream=[source])
   def process(data):
       return {"result": sum(data["data"])}
   
   if __name__ == "__main__":
       result = run_strategy()
   ```

2. **DAG 제출** (SDK → Gateway):
   ```python
   # sdk/clients/gateway_client.py
   def submit_dag(dag):
       response = requests.post(
           f"{GATEWAY_URL}/v1/gateway/strategies", 
           data=dag.SerializeToString(),
           headers={"Content-Type": "application/x-protobuf"}
       )
       return StrategyResponse.FromString(response.content)
   ```

3. **작업 큐 등록 및 처리** (Gateway):
   ```python
   # gateway/services/work_queue_service.py
   def enqueue_strategy_execution(strategy_request):
       work_id = str(uuid.uuid4())
       work_item = WorkItem(
           id=work_id,
           type=WorkType.STRATEGY_EXECUTION,
           payload=strategy_request.SerializeToString(),
           status=WorkStatus.PENDING
       )
       self.queue_repository.push(work_item)
       return work_id
   ```

4. **메타데이터 조회** (Gateway → DAG Manager):
   ```python
   # gateway/clients/dag_manager_client.py
   def get_node_metadata(node_ids):
       response = requests.post(
           f"{DAG_MANAGER_URL}/v1/dag-manager/nodes/metadata",
           data=NodeIdList(node_ids=node_ids).SerializeToString(),
           headers={"Content-Type": "application/x-protobuf"}
       )
       return NodeMetadataList.FromString(response.content).items
   ```

5. **QueryNode TAG 처리** (Gateway):
   ```python
   # gateway/services/query_node_resolver.py
   def resolve_query_nodes(nodes):
       query_nodes = [n for n in nodes if n.type == NodeType.QUERY]
       for qnode in query_nodes:
           tags = qnode.tags or []
           # DAG Manager에서 태그 기반 노드 조회
           matching_nodes = self.dag_manager_client.get_nodes_by_tags(tags)
           qnode.resolved_upstream = [n.id for n in matching_nodes]
       return nodes
   ```

6. **글로벌 DAG 노드 생성** (Gateway → DAG Manager):
   ```python
   # gateway/services/dag_sync_service.py
   def create_missing_nodes(nodes):
       existing_nodes = self.dag_manager_client.get_nodes_by_ids(
           [n.id for n in nodes]
       )
       existing_ids = set(n.id for n in existing_nodes)
       
       # 신규 노드만 생성 요청
       new_nodes = [n for n in nodes if n.id not in existing_ids]
       if new_nodes:
           self.dag_manager_client.create_nodes(new_nodes)
   ```

7. **실행 노드 콜백** (Gateway → SDK):
   ```python
   # gateway/services/callback_service.py
   def notify_executable_nodes(strategy_id, node_ids):
       callback_url = self.get_callback_url(strategy_id)
       if callback_url:
           requests.post(
               callback_url,
               json={
                   "type": "EXECUTABLE_NODES",
                   "strategy_id": strategy_id,
                   "node_ids": node_ids
               }
           )
   ```

8. **노드 실행** (SDK):
   ```python
   # sdk/core/node_executor.py
   def execute_nodes(node_ids):
       for node_id in node_ids:
           # 노드 정보는 반드시 Registry(또는 DAG Manager) API를 통해 조회해야 하며,
           # Gateway는 registry 또는 NODE_REGISTRY를 직접 소유/관리하지 않음
           node = get_node_from_registry(node_id)  # 예시 함수명
           if node:
               # 업스트림 데이터 수집
               upstream_data = get_upstream_data(node)
               # 노드 함수 실행
               result = node.func(**upstream_data)
               # 결과 저장
               save_node_result(node_id, result)
   ```

### 2.2 글로벌 DAG 변경 이벤트 처리

1. **DAG 변경 이벤트 발행** (DAG Manager):
   ```python
   # dag_manager/services/event_publisher.py
   def publish_node_status_change(node_id, status):
       event = NodeStatusChangeEvent(
           node_id=node_id,
           status=status,
           timestamp=datetime.now()
       )
       self.event_repository.publish(
           "node.status.change", event.model_dump()
       )
   ```

2. **이벤트 구독 및 처리** (Gateway):
   ```python
   # gateway/services/event_subscriber.py
   def handle_node_status_change(event_data):
       event = NodeStatusChangeEvent.model_validate(event_data)
       # 관련 QueryNode 검색
       affected_query_nodes = self.query_node_service.find_by_tag_node(
           event.node_id
       )
       # 영향 받는 전략 파일 찾기
       affected_strategies = self.strategy_service.find_by_query_nodes(
           affected_query_nodes
       )
       # 각 전략에 상태 변경 통지
       for strategy in affected_strategies:
           self.callback_service.notify_dag_change(
               strategy.id, affected_query_nodes
           )
   ```

3. **SDK 콜백 및 업데이트** (Gateway → SDK):
   ```python
   # gateway/services/callback_service.py
   def notify_dag_change(strategy_id, affected_nodes):
       callback_url = self.get_callback_url(strategy_id)
       if callback_url:
           requests.post(
               callback_url,
               json={
                   "type": "DAG_CHANGE",
                   "strategy_id": strategy_id,
                   "affected_nodes": [n.id for n in affected_nodes]
               }
           )
   ```

4. **SDK 측 처리** (SDK):
   ```python
   # sdk/core/callback_handler.py
   def handle_dag_change(event_data):
       strategy_id = event_data["strategy_id"]
       affected_nodes = event_data["affected_nodes"]
       
       # QueryNode의 경우, 반드시 Registry(또는 DAG Manager) API를 통해 업스트림 재조회
       for node_id in affected_nodes:
           node = get_node_from_registry(node_id)  # 예시 함수명
           if node and node.type == NodeType.QUERY:
               # Gateway에 재조회 요청
               updated_upstream = gateway_client.get_query_node_upstream(node_id)
               # 노드 업스트림 갱신
               node.update_upstream(updated_upstream)
               
       # 실행 가능한 노드가 있으면 실행
       executable = gateway_client.get_executable_nodes(strategy_id)
       if executable:
           node_executor.execute_nodes(executable)
   ```


## 3. 설계의 장점 및 구현 세부사항

### 3.1 관심사 분리(SoC) 극대화
- **명확한 책임 경계**:
  - DAG Manager: 글로벌 DAG/스트림 관리 (Neo4j + Kafka)
  - Gateway: 조율/중계/작업 큐 관리 (Redis)
  - SDK: 전략 작성/실행/DAG 추출 (Python API)

- **독립적 확장/유지보수**:
  ```python
  # 각 서비스별 독립 도커파일 예시
  # dag_manager.Dockerfile
  FROM python:3.9-slim
  WORKDIR /app
  COPY pyproject.toml .
  RUN pip install ".[dag-manager]"
  CMD ["uvicorn", "qmtl.dag_manager.api:app", "--host", "0.0.0.0"]
  
  # gateway.Dockerfile
  FROM python:3.9-slim
  WORKDIR /app
  COPY pyproject.toml .
  RUN pip install ".[gateway]"
  CMD ["uvicorn", "qmtl.gateway.api:app", "--host", "0.0.0.0"]
  ```

### 3.2 운영/장애 처리 일관성
- **DAG과 스트림 함께 관리**:
  ```python
  # dag_manager/services/node_creation_service.py
  def create_node_with_stream(node):
      # 트랜잭션 시작
      tx = self.transaction_manager.begin()
      try:
          # 1. 노드 메타데이터 저장
          node_id = self.node_repository.create(node)
          
          # 2. 필요시 스트림(토픽) 생성
          if node.requires_stream:
              stream_id = self.stream_service.create_stream(
                  node_id=node_id,
                  settings=node.stream_settings
              )
              # 노드-스트림 연결 업데이트
              self.node_repository.update_stream(node_id, stream_id)
              
          # 3. 의존성 관계 등록
          if node.upstream:
              self.dependency_service.create_dependencies(
                  node_id, node.upstream
              )
              
          tx.commit()
          return node_id
      except Exception as e:
          tx.rollback()
          raise NodeCreationError(f"Failed to create node: {str(e)}")
  ```

### 3.3 Gateway 작업 큐 구조
- **Redis 기반 견고한 작업 큐**:
  ```python
  # gateway/repositories/redis_queue_repository.py
  class RedisQueueRepository:
      def __init__(self, redis_client):
          self.redis = redis_client
          self.queue_key = "qmtl:gateway:work_queue"
          self.processing_key = "qmtl:gateway:processing"
          self.results_key = "qmtl:gateway:results"
      
      def push(self, work_item):
          """작업 큐에 항목 추가 (protobuf 바이너리)"""
          serialized = work_item.SerializeToString()
          self.redis.lpush(self.queue_key, serialized)
          
      def pop(self, timeout=0):
          raw = self.redis.brpoplpush(
              self.queue_key, self.processing_key, timeout
          )
          if raw:
              return WorkItem.FromString(raw)
          return None
      
      def complete(self, work_id, result=None):
          """작업 완료 처리 및 결과 저장"""
          # 처리 중 목록에서 찾기
          pattern = f'*"id":"{work_id}"*'
          for key in self.redis.scan_iter(match=pattern, count=100):
              work_raw = self.redis.get(key)
              work = WorkItem.model_validate(json.loads(work_raw))
              
              # 결과 저장
              work.status = WorkStatus.COMPLETED
              work.result = result
              work.completed_at = datetime.now()
              
              # 결과 목록에 저장
              self.redis.hset(
                  self.results_key, 
                  work_id,
                  json.dumps(work.model_dump())
              )
              # TTL 설정 (예: 1시간)
              self.redis.expire(f"{self.results_key}:{work_id}", 3600)
              
              # 처리 중 목록에서 제거
              self.redis.lrem(self.processing_key, 1, work_raw)
              return True
          return False
  ```

### 3.4 상태/콜백 전달 방식
- **초기: REST 기반 폴링 (protobuf 직렬화/역직렬화 적용)**
  ```python
  # sdk/clients/gateway_client.py
  def poll_strategy_status(strategy_id, interval=5):
      """전략 상태 폴링 (protobuf 바이너리 응답 기준)"""
      while True:
          response = requests.get(
              f"{GATEWAY_URL}/v1/gateway/strategies/{strategy_id}/status",
              headers={"Accept": "application/x-protobuf"}
          )
          # protobuf 바이너리 응답을 decode
          status = StrategyStatus.FromString(response.content)
          # 종료 조건 체크
          if status.state in [State.COMPLETED, State.FAILED, State.CANCELED]:
              return status
          # 실행 가능한 노드가 있으면 실행
          if status.executable_nodes:
              execute_nodes(status.executable_nodes)
          time.sleep(interval)
  ```

- **콜백/이벤트 전달도 protobuf 바이너리로 통일**
  ```python
  # gateway/services/callback_service.py
  def notify_executable_nodes(strategy_id, node_ids):
      callback_url = get_callback_url(strategy_id)
      if callback_url:
          # 콜백 페이로드를 protobuf 메시지로 생성 후 SerializeToString
          payload = ExecutableNodesEvent(
              strategy_id=strategy_id,
              node_ids=node_ids
          ).SerializeToString()
          requests.post(
              callback_url,
              data=payload,  # 바이너리 전송
              headers={"Content-Type": "application/x-protobuf"}
          )
  ```

- **내부 서비스 간 데이터 교환, 큐, 브로커, 테스트 등도 모두 protobuf SerializeToString/FromString 사용**
  ```python
  # gateway/repositories/redis_queue_repository.py
  class RedisQueueRepository:
      ...
      def push(self, work_item):
          """작업 큐에 항목 추가 (protobuf 바이너리)"""
          serialized = work_item.SerializeToString()
          self.redis.lpush(self.queue_key, serialized)
      def pop(self, timeout=0):
          raw = self.redis.brpoplpush(
              self.queue_key, self.processing_key, timeout
          )
          if raw:
              return WorkItem.FromString(raw)
          return None
  ```

- **테스트, golden test, round-trip test 등도 protobuf SerializeToString/FromString 기준**
  ```python
  def test_protobuf_round_trip():
      node = Node(id="n1", ...)
      payload = node.SerializeToString()
      node2 = Node.FromString(payload)
      assert node == node2
  ```


## 결론: protobuf 기반 contract-first 아키텍처의 일관성
- QMTL의 모든 데이터 계약, API, 이벤트, 테스트, 문서화, 자동화는 protobuf 스키마를 단일 진실 소스로 삼아 관리
- 서비스/SDK/테스트/문서화/자동화 등 모든 계층에서 protobuf 타입만 사용함으로써, 언어/플랫폼 독립적이고, 일관성/신뢰성/생산성이 극대화된 구조를 실현
- 기존 Python 모델 패키지 방식은 완전히 대체되며, protobuf 스키마 관리가 표준임을 명확히 함

## 결론(추가):
- protobuf contract 기반 데이터 구조는 외부 API에서 조회(read)만 허용, 조작은 내부 서비스 계층에서만 수행
- 이를 통해 데이터 무결성, 관심사 분리, 서비스 간 결합도 최소화, 유지보수성 극대화

### [protobuf vs json 직렬화/역직렬화 표준]
- **API, 이벤트, 서비스 간 데이터 교환, 테스트 등 모든 실제 데이터 페이로드는 protobuf 직렬화/역직렬화가 표준**
  - 예: `payload = node.SerializeToString()` (protobuf 직렬화), `node2 = Node.FromString(payload)` (protobuf 역직렬화)
  - API, 메시지 브로커, 내부 큐, 테스트 golden data 등에서 json 대신 protobuf 바이너리 포맷 사용
- **JSON은 human-friendly 문서, 디버깅, 외부 문서화 용도로만 사용**
  - 필요시 protobuf 타입에서 json 변환 유틸리티 제공 (예: `MessageToJson(node)`, `Parse(node_json, Node())` 등)
  - OpenAPI/문서화/예제 등은 protobuf 스키마 → json schema 변환을 통해 자동 생성
- **테스트/검증/golden test 등도 protobuf 직렬화 기반**
  - round-trip test, schema validation, golden test 등은 모두 protobuf SerializeToString/FromString 기준으로 작성
- **기존 model_dump, model_validate, model_json_schema 등 Pydantic/json 기반 메서드는 사용하지 않음**
  - 모든 데이터 구조/계약/테스트/문서화의 단일 진실 소스는 protobuf 스키마와 그로부터 생성된 타입/직렬화 코드임을 반복 강조

---

### [Neo4j TAG 인덱싱 설계 원칙]
- **QueryNode의 TAG 기반 조회 성능을 위해, Neo4j에서 Node의 `tags` 속성은 반드시 인덱싱해야 함**
- 인덱스 생성 예시(Cypher):
  ```cypher
  CREATE INDEX node_tags_index IF NOT EXISTS FOR (n:Node) ON (n.tags)
  ```
- 인덱스가 있으면 TAG 기반 노드 조회가 대규모 데이터셋에서도 빠르게 동작하며, QueryNode의 실시간성/확장성 보장
- 인덱스 생성은 마이그레이션 스크립트, 초기화 코드, 또는 운영 Neo4j 관리 정책에 반드시 포함
- Neo4j 4.x 이상에서는 리스트 타입 속성(`tags: [string]`)도 인덱싱 지원
- **설계/운영 가이드**: TAG 기반 쿼리, QueryNode 해석, DAG 동적 해석 등 모든 TAG 관련 로직은 인덱스 활용을 전제로 구현

## 4. DAG Manager 재기동 및 장애 복구 설계

### 4.1 Stateless 설계
- **DAG Manager는 완전한 stateless 서비스로 설계**
  - 모든 상태(노드, DAG, 의존성, 메타데이터 등)는 Neo4j(그래프 DB) 또는 외부 메시지 브로커(Kafka/Redis 등)에만 저장
  - 서비스 인스턴스는 언제든지 재기동/스케일아웃/롤링업데이트 가능하며, 자체적으로 상태를 보존하지 않음
  - 장애 발생 시에도 서비스 재기동만으로 정상 동작 복구 가능

### 4.2 내구성 있는 큐/브로커 사용
- **모든 작업 큐/이벤트 브로커는 durability(내구성) 옵션을 활성화하여 운영**
  - Kafka/Redpanda: acks=all, min.insync.replicas, log.durability 등 내구성 옵션 필수 적용
  - Redis: AOF(append-only file) 또는 RDB 스냅샷 활성화, 장애 시 데이터 유실 최소화
  - 미처리 메시지/작업은 서비스 재기동 후에도 반드시 재처리됨을 보장

### 4.3 멱등성 보장
- **모든 작업/이벤트 처리 로직은 멱등성(idempotency)을 보장**
  - 동일 작업/이벤트가 중복 전달되어도 결과가 변하지 않도록 설계
  - 예: 노드 생성/업데이트/이벤트 발행 시 unique key, idempotency key, 상태 체크 등 적용
  - 장애/재기동/네트워크 이슈 등으로 인한 중복 처리에도 데이터 일관성 유지

### 4.4 초기화/복구 루틴
- **서비스 기동 시 상태 점검 및 복구 루틴을 반드시 수행**
  - Neo4j, 브로커, 큐 등 외부 시스템 연결 및 상태 점검
  - 미완료 작업/이벤트/트랜잭션 조회 및 재처리
  - 인덱스, 스키마, 필수 데이터 구조 자동 점검 및 생성
  - 예: Neo4j TAG 인덱스, Kafka 토픽, Redis 큐 등

#### 예시: 서비스 기동 시 복구 루틴
```python
# dag_manager/boot.py

def initialize_and_recover():
    # 1. Neo4j 연결 및 인덱스 점검
    neo4j.ensure_index('node_tags_index', 'Node', 'tags')
    # 2. Kafka 토픽/파티션 점검
    kafka.ensure_topics(['dag-events', 'node-status'])
    # 3. Redis 큐/브로커 점검
    redis.ensure_queue('qmtl:dag:work_queue')
    # 4. 미완료 작업/이벤트 재처리
    for work in redis.get_pending_works():
        process_work(work)
    for event in kafka.get_uncommitted_events():
        handle_event(event)
    # 5. 기타 상태 점검 및 복구
    ...
```
- 위 루틴은 서비스가 언제든지 재기동/스케일아웃/장애 복구되어도 데이터 일관성과 내구성을 보장함

---

## 5. CHANGELOG (Architecture NextGen)

### [YYYY-MM-DD] QMTL NextGen Architecture Major Update
- Split QMTL into three independent components: DAG Manager, Gateway, SDK
- All data contracts, APIs, and events migrated to bebop-based schema management
- All API endpoints are read-only for bebop contract models; mutations handled internally
- Neo4j TAG 인덱싱 설계 및 Cypher 예시 추가
- DAG Manager stateless 설계, durability, idempotency, robust recovery/initialization routines 문서화
- 모든 워크플로우, 콜백, 테스트 코드 예시를 bebop encode/decode 기반으로 변경
- 장애 복구, 캐시 손실, 이벤트/큐 동기화, 트랜잭션 일관성, 복구 방안 등 리스크 및 대응책 추가
- Gateway 장애/재기동 시 데이터 일관성 및 복구 설계(권장안, 예시, 한계 등) 섹션 추가

### [Gateway 장애/재기동 시 데이터 일관성 및 복구 설계]

#### 1. 단순 캐시 삭제 + 실패 신호의 한계
- Gateway 장애/종료 시 Redis 캐시를 삭제하고, 전략 SDK에 실패 신호를 보내는 방식은
  - 재기동 후 깨끗한 상태에서 시작할 수 있다는 장점이 있으나,
  - 진행 중이던 작업(큐에 있던 미처리 작업 등)이 모두 소실되고, 불필요하게 많은 작업이 실패 처리될 수 있음
  - 장애가 일시적일 때도 모든 작업이 실패로 처리되어, 복구 후 수동 재시작/재처리가 필요
  - 장애 원인에 따라 SDK가 중복 실행, 데이터 불일치 등 부작용이 발생할 수 있음

#### 2. 권장 대안: 내구성, 멱등성, 자동 복구, 상태 기반 알림 결합
- **Redis 내구성 옵션 활성화**: AOF(Append Only File) 또는 RDB 스냅샷을 활성화하여, Gateway 재기동 시에도 큐/상태 데이터가 최대한 보존되도록 설계
- **작업 큐의 멱등성 보장**: 각 작업(WorkItem)에 고유 ID를 부여하고, Gateway가 재기동 후에도 중복 작업이 실행되지 않도록 처리(예: processed set, 상태 체크 등)
- **미처리 작업 자동 복구**: Gateway 재기동 시 Redis 큐에 남아있는 미처리 작업을 자동으로 재처리 (예: brpoplpush, pending queue, 상태 플래그 활용)
- **SDK에 실패 신호 대신 '진행 중/재시도' 신호 제공**: 장애가 일시적일 수 있으므로, SDK에는 '작업이 지연/재시도 중'임을 알리고, 일정 시간/횟수 초과 시에만 '실패' 신호를 보내는 것이 더 안전
- **모니터링/알림 연동**: Gateway 장애/재기동/작업 실패 등 주요 이벤트를 운영자/사용자에게 실시간 알림(예: Slack, Email, 대시보드 등)으로 제공

#### 3. 설계 예시 (Gateway 작업 큐/복구)
```python
# gateway/services/boot.py

def initialize_and_recover():
    # 1. Redis durability 옵션 점검 (AOF/RDB)
    redis.ensure_durability()
    # 2. 미처리 작업 복구
    for work in redis.get_pending_works():
        if not redis.is_processed(work.id):
            process_work(work)
    # 3. 상태 기반 알림
    for work in redis.get_failed_works():
        if work.retry_count < MAX_RETRY:
            retry_work(work)
        else:
            notify_sdk_failure(work.strategy_id, work.id)
    # 4. 운영자 알림
    if redis.detected_crash():
        send_ops_alert('Gateway 재기동 및 복구 루틴 실행됨')
```

#### 4. 요약
- 단순 캐시 삭제 + 실패 신호는 데이터 유실/불필요한 실패 증가 위험이 있음
- 내구성, 멱등성, 자동 복구, 상태 기반 알림을 결합하면 Gateway 재기동 시에도 데이터 유실/중복 실행/불필요한 실패 없이 안정적으로 운영 가능
- Redis durability, 작업 큐 멱등성, 미처리 작업 복구, 상태 기반 알림, 운영자 모니터링을 반드시 설계에 포함할 것

---

# [중요 아키텍처 원칙: Gateway와 Registry 책임 분리]

> **NG-1,2 단계에서 gateway가 registry(레지스트리)를 직접 가지도록 설계/코드가 분리된 부분은 잘못된 구조입니다.**
> - Gateway는 registry(노드/전략/의존성/메타데이터 관리) 책임을 절대 가지지 않습니다.
> - Gateway가 registry를 직접 참조하거나 관리하는 설계/코드/예시/표현은 모두 제거해야 합니다.
> - Gateway가 노드/전략/의존성/메타데이터 정보가 필요할 때는 반드시 Registry(또는 DAG Manager) API를 통해 조회/조율만 수행해야 합니다.
> - 모든 데이터/메타데이터 관리는 Registry(또는 DAG Manager)에서만 담당합니다.
> - 서비스별 책임 분류표, 워크플로우 예시, 설명 등에서 gateway와 registry의 경계를 명확히 구분해야 합니다.

---

## QMTL NextGen 서비스별 책임 분류표 (NG-1-1)

| 서비스         | 주요 책임/역할                                                         | 코드/디렉토리 예시                                 |
|----------------|---------------------------------------------------------------------|---------------------------------------------------|
| **DAG Manager**| 글로벌 DAG, 노드, 의존성, 메타데이터, 이벤트, 토픽 관리                | orchestrator/, models/datanode.py, models/strategy.py, models/event.py 등 |
| **Gateway**    | 작업 큐, DAG 동기화, 콜백, 상태 추적, QueryNode 해석, 중계             | gateway/services/, gateway/api.py, gateway/api_callback.py 등 |
| **SDK**        | 사용자 전략 작성/실행, DAG 추출, Gateway 통신, 노드 실행, 콜백 처리     | sdk/, models/analyzer.py, models/template.py 등    |
| **공통**       | 설정, DB/Redis/HTTP, 유틸리티, 공통 모델                              | common/, models/(공통모델)                         |

# 워크플로 오케스트레이션 Radon 정비 계획

## 범위
- 대상 모듈:
  - `qmtl/services/dagmanager/diff_service.py`, `kafka_admin.py`
  - `qmtl/services/gateway/strategy_submission.py`, `dagmanager_client.py`, `worker.py`
  - `qmtl/runtime/sdk/gateway_client.py`, `tag_manager_service.py`, `backfill_engine.py`, `activation_manager.py`
- 연관 이슈:
  - #1549 워크플로 오케스트레이션 복잡도 정리 (메타)
  - #1563 DiffService 큐/센티넬 오케스트레이션 리팩터링
  - #1564 KafkaAdmin 토픽 검증/생성 오케스트레이션 정리
  - #1565 Gateway 전략 제출 컨텍스트/큐맵/월드 바인딩 파이프라인 정리
  - #1566 Gateway DAG diff 워커 및 gRPC 클라이언트 오케스트레이션 정리
  - #1567 Runtime SDK Gateway/태그/백필/액티베이션 오케스트레이션 정리

이 문서는 위 이슈들을 통해 진행한 워크플로 오케스트레이션 경로의 복잡도 정비 결과를 요약하고, 이후 작업에서 재사용할 설계 패턴을 정리한다.
범위 노트(2025-11-24): Gateway + DAG Manager + Runtime SDK 오케스트레이션에 대한 최신 라돈 현황은 이 문서로 통합되었으며, 기존 Control-Plane/Runtime SDK 라돈 계획 문서는 상태를 반영한 후 제거했다.

## 기본 radon 스냅샷 (계획 수립 시점)

다음 함수들은 radon CC 리포트 기준으로 C/D 급 복잡도를 보이면서, DAG Diff·토픽 오케스트레이션·전략 제출·Runtime SDK 오케스트레이션의 핵심 경로를 형성했다.

| 파일 | 함수 | CC 등급 / 점수 | 비고 |
| --- | --- | --- | --- |
| `services/dagmanager/server.py` | `_KafkaAdminClient.list_topics` | D / 21 | 토픽 메타데이터 조회 + 검증 + 예외 처리 일체. |
| `services/dagmanager/diff_service.py` | `DiffService._hash_compare` | C / 20 | 큐 바인딩, cross-context 검증, 센티넬/CRC/메트릭 처리까지 한 함수에 집중. |
| `services/dagmanager/kafka_admin.py` | `KafkaAdmin._verify_topic` | C / 13 | 토픽 존재/콜리전/파라미터 검증과 예외 흐름이 혼재. |
| `services/gateway/strategy_submission.py` | `StrategySubmissionHelper._build_queue_outputs` | C / 14 | Diff 호출 + fallback 큐맵 + CRC 센티넬까지 단일 함수에서 오케스트레이션. |
| `services/gateway/strategy_submission.py` | `StrategySubmissionHelper._persist_world_bindings` | C / 12 | DB/WorldService 양쪽 바인딩/예외 처리가 한 함수에 섞여 있음. |
| `services/gateway/dagmanager_client.py` | `DagManagerClient.diff` | C / 11 | DiffRequest 생성, gRPC 스트림 수집, CRC 검증, breaker/재시도, namespace 적용까지 모두 포함. |
| `services/gateway/worker.py` | `StrategyWorker._process` | C / 14 | Redis 상태 로딩, diff 호출, FSM 전이, WS 브로드캐스트, 알림까지 단일 함수. |
| `runtime/sdk/trade_dispatcher.py` | `TradeOrderDispatcher.dispatch` | C / 20 | 검증·게이팅·중복 제거·HTTP/Kafka 전송까지 단일 메서드에서 처리. |
| `runtime/sdk/gateway_client.py` | `GatewayClient.post_strategy` | C / 14 | HTTP 요청 구성, breaker, status-code 매핑, pydantic 검증이 한 함수에 집중. |
| `runtime/sdk/tag_manager_service.py` | `TagManagerService.apply_queue_map` | C / 16 | 큐맵 적용/로그/상태 갱신이 섞여 있어 분기 복잡도가 높음. |
| `runtime/sdk/backfill_engine.py` | `BackfillEngine._publish_metadata` | C / 17 | 메타데이터 구성·검증·Gateway 호출이 한 메서드에 결합. |
| `runtime/sdk/activation_manager.py` | `ActivationManager.start` | C / 14 | 활성화 시작, 이벤트 스트림 구독, 상태 초기화 오케스트레이션이 단일 함수에 집중. |

## 결과 요약 (2025-11-16 기준)

서브 이슈 #1563–#1567 을 반영한 이후, 위 경로들의 CC 등급은 다음과 같이 개선되었다.

- DAG Manager
  - `_KafkaAdminClient.list_topics` (D / 21) → **A / 2** (#1563)
  - `DiffService._hash_compare` (C / 20) → **A / 1** (#1563) — 토픽 바인딩 계획/실행 분리, Result 타입 도입.
  - `KafkaAdmin._verify_topic` (C / 13) → **A / 1** (#1564) — `TopicVerificationPolicy` / `TopicEnsureResult` 도입.
- Gateway
  - `StrategySubmissionHelper._build_queue_outputs` (C / 14) → **A / 3** (#1565) — `QueueResolution` Result 객체와 `_resolve_queue_map` 스텝으로 분리.
  - `StrategySubmissionHelper._persist_world_bindings` (C / 12) → **A / 3** (#1565) — 바인딩 대상 계산과 WorldService sync 를 개별 헬퍼로 분리.
  - `DagManagerClient.diff` (C / 11) → **A / 3** (#1566) — `DiffStreamClient` 헬퍼에 스트림 수집·CRC 검증·namespace 적용 위임.
  - `StrategyWorker._process` (C / 14) → **A / 4** (#1566) — 락 획득, 컨텍스트 로딩, diff 실행, 브로드캐스트, FSM 전이를 개별 스텝 메서드로 분리.
- Runtime SDK
  - `TradeOrderDispatcher.dispatch` (C / 20) → **A / 3** — `DispatchStep` 체인 기반 Pipeline 패턴.
  - `GatewayClient.post_strategy` (C / 14) → **A / 1** (#1567) — `GatewayCallResult` Result 타입 + `_post` / `_parse_strategy_response` 분리.
  - `TagManagerService.apply_queue_map` (C / 16) → **A / 3** (#1567) — 매칭 수집/적용/로깅을 `_collect_matches` / `_apply_*_mapping` / `_log_execute_change` 로 분리.
  - `BackfillEngine._publish_metadata` (C / 17) → **A / 5** (#1567) — 메타데이터 구성과 Gateway 호출을 `_build_metadata_payload` / `_publish_metadata` 로 분리.
  - `ActivationManager.start` (C / 14) → **A / 5** (#1567) — 시작 시퀀스를 `_start_existing_client` / `_start_via_gateway` / `_schedule_polling` 등으로 분리.

여전히 C 급 복잡도를 갖는 함수가 일부 존재하지만, 이 문서의 범위는 위 오케스트레이션 경로에 한정된다. 데이터 정규화·백필 경로는 `maintenance/radon_normalization_backfill.md`에서 추적하고, WorldService 스키마/alpha 경로는 #1514 작업 완료로 `architecture/worldservice.md`와 `world/rebalancing.md`에 흡수되어 별도 radon 계획을 종료한다.

## 공통 불량 패턴 요약

정비 전 오케스트레이션 경로에는 다음과 같은 공통 불량 패턴이 반복되었다.

- 단일 메서드에 \"검증 → 외부 호출 → 재시도/백오프 → 결과 병합 → 예외 처리 → 메트릭/로그 방출\"이 모두 포함되어 radon CC 가 자연스럽게 C/D 로 상승.
- 네트워크/브로커/WorldService 오류 처리와 다운그레이드 정책이 중첩된 if/try 블록으로만 표현되어, happy-path 를 읽기 어렵고 테스트 단위도 커짐.
- 재시도 정책, 로깅 포맷, 에러 매핑이 여러 모듈에서 중복 구현되어, 변경 시 동기화 비용이 큼.
- 성공/부분 성공/실패가 bool 플래그, `None` 반환, 예외, dict 기반 에러 메시지가 혼용된 형태로 표현되어 호출자 계층에서 분기 규칙이 일관되지 않음.

## 적용 패턴 / 설계 방향

위 불량 패턴을 해소하기 위해 다음과 같은 공통 설계 패턴을 적용했다.

- **Pipeline / Chain of Responsibility**
  - `TradeOrderDispatcher`, `StrategySubmissionHelper`, `StrategyWorker` 등에서 공통적으로, 작은 스텝 객체/메서드(예: `ComputeContextStep`, `DiffQueueMapStep`, `WorldBindingPersistStep`)를 정의하고, 메인 오케스트레이터는 스텝 구성과 실행 순서만 관리하도록 단순화했다.
- **공통 Result 타입**
  - `GatewayCallResult`, `StrategySubmissionResult`, `DiffOutcome`, `QueueResolution`, `TopicEnsureResult` 와 같은 Result 객체를 도입해, 성공/부분 성공/실패 상태와 진단 정보를 명시적으로 표현했다.
  - 호출자는 bool/예외/None 혼용 대신 Result 객체의 `ok` 플래그나 명시적 필드를 기준으로 분기할 수 있다.
- **공통 헬퍼/데코레이터 추출**
  - Kafka 토픽 검증/생성(`TopicVerificationPolicy`, `TopicCreateRetryStrategy`), DAG Diff 스트림 수집(`DiffStreamClient`), Gateway HTTP 호출(`GatewayClient._post`), WorldService 컨텍스트 병합(`ComputeContextService`)을 헬퍼·유틸 계층으로 분리했다.
  - 오케스트레이션 함수는 이 헬퍼들을 조합하는 역할에 집중하도록 하여, 책임과 복잡도를 줄였다.
- **다운그레이드/폴백 정책의 명시적 모델링**
  - Diff 실패 시 TagQuery fallback, CRC sentinel fallback, WorldService stale/unavailable 시 compute 컨텍스트 다운그레이드 등은 Result 타입과 전용 메서드로 표현해, 정책이 코드 상에서 명확히 드러나도록 했다.

## 검증 체크리스트

워크플로 오케스트레이션 경로 변경을 검증하기 위한 최소 체크리스트는 다음과 같다.

- radon 복잡도/MI 확인
  - `uv run --with radon -m radon cc -s qmtl/services/dagmanager/diff_service.py qmtl/services/dagmanager/kafka_admin.py`
  - `uv run --with radon -m radon cc -s qmtl/services/gateway/strategy_submission.py qmtl/services/gateway/dagmanager_client.py qmtl/services/gateway/worker.py`
  - `uv run --with radon -m radon cc -s qmtl/runtime/sdk/gateway_client.py qmtl/runtime/sdk/tag_manager_service.py qmtl/runtime/sdk/backfill_engine.py qmtl/runtime/sdk/activation_manager.py`
  - 필요 시 전체 스냅샷: `uv run --with radon -m radon cc -s -n C qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- 회귀 테스트
  - DiffService, Gateway, Runtime SDK 관련 테스트 모듈: `uv run -m pytest -W error -n auto qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- 문서 빌드
  - `uv run mkdocs build`

이 체크리스트와 위 서브 이슈들을 기준으로, #1549 에서 합의한 워크플로 오케스트레이션 복잡도 정리는 완료된 것으로 간주한다.

### RPC 어댑터 계획(#1554, #1584)과의 연계

- DAG diff 실행 경로(`DagManagerClient.diff` → `DiffExecutor.run` → `StrategyWorker._diff_strategy`)는 이미 위 패턴을 적용한 상태이며, radon 기준으로 A/B 등급을 유지한다.
- RPC 어댑터 Command/Facade 설계안(#1554, #1581, #1584)은 이 경로를 대표 사례로 간주하며, 자세한 레이어링 설명은 `architecture/rpc_adapters.md` 문서를 따른다.
- #1584 에서는 추가 코드 변경 없이, 본 문서와 RPC 어댑터 설계 문서 간의 정렬 상태를 검증하고 메타 이슈(#1554)에서 diff 경로를 완료된 상태로 표시한다.

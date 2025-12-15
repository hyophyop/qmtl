---
title: "RPC 어댑터 Command/Facade 설계안"
tags:
  - maintenance
  - architecture
  - rpc
  - gateway
  - dag-manager
author: "QMTL Team"
last_modified: 2025-12-15
---

{{ nav_links() }}

# RPC 어댑터 Command/Facade 설계안

## 0. 목적과 Core Loop 상 위치

- 목적: Gateway/DAG Manager/WorldService 및 Runtime SDK 계층에서 사용하는 RPC/서비스 어댑터의 복잡도를 줄이기 위한 공통 설계 패턴을 정의합니다.
- Core Loop 상 위치: Core Loop 각 단계(전략 제출, 평가, 활성화, 리밸런싱)에서 호출되는 내부/외부 RPC 경로를 **명시적인 Command/Facade 계층**으로 감싸, 아키텍처 경계가 코드 수준에서도 유지되도록 하는 유지보수/설계 계획입니다.

## 1. 범위 및 배경

이 문서는 Gateway/DAG Manager/WorldService 및 Runtime SDK 계층에서 사용하는 RPC/서비스 어댑터의 복잡도를 줄이기 위한 공통 설계 패턴을 정의한다.

- 메타 이슈: #1554 RPC·서비스 어댑터 복잡도 개선
- 설계/공통 모듈 이슈: #1581

### 1.1 radon 기준 대상 함수 스냅샷

`uv run --with radon -m radon cc -s -n C qmtl/runtime/sdk qmtl/services/gateway` 기준, RPC/어댑터 관련 C 등급 함수의 예시는 다음과 같다(2025‑11‑16 기준).

| 파일 | 함수 | CC 등급 / 점수 | 역할 요약 |
| --- | --- | --- | --- |
| `services/gateway/world_client.py` | `WorldServiceClient.get_decide` | C / 17 | WorldService 결정 HTTP 호출 + TTL 캐시 + 헤더/본문 기반 TTL 파싱 + 에러/폴백 처리 |
| `services/gateway/world_client.py` | `WorldServiceClient._iter_rebalance_payloads` | C / 12 | 리밸런싱 스키마 버전별 페이로드 생성 및 폴백 전개 |
| `services/gateway/ownership.py` | `OwnershipManager.acquire` | C / 16 | Redis 락 획득/타임아웃/에러 분기를 한 함수에 결합 |
| `services/gateway/strategy_submission.py` | `StrategySubmissionHelper._resolve_queue_map` | C / 11 | DAG diff 결과/월드 컨텍스트 기반 큐맵 해석 및 폴백 |
| `services/gateway/controlbus_consumer.py` | `ControlBusConsumer._parse_kafka_message` | C / 15 | ControlBus 메시지 디코딩·검증·분기 처리 |
| `services/gateway/api.py` | `create_app` | C / 18 | Gateway API/라우터/미들웨어 구성 및 의존성 주입 |
| `services/gateway/cli.py` | `_main` | C / 18 | CLI 인자 파싱·환경 구성·서비스 부트스트랩 |

참고로, 이전 스냅샷에서 C 등급이었던 다음 경로들은 이미 개별 이슈에서 정비되었다.

- `runtime/sdk/gateway_client.GatewayClient.post_strategy` — #1582
- `services/gateway/dagmanager_client.DagManagerClient.diff`, `services/gateway/submission/diff_executor.DiffExecutor.run`, `services/gateway/worker.StrategyWorker._process` — 워크플로 오케스트레이션 Radon 계획 문서와 연계.

이 문서는 위/유사 경로에 공통으로 적용할 수 있는 Command/Facade·응답 파서·에러 매퍼 설계를 정의하고, 이후 서브 이슈(#1582, #1583, #1584 등)에서 사용할 가이드를 제공한다.

## 2. 레이어 모델

RPC 어댑터 경로는 다음과 같은 최소 레이어로 나눈다.

1. **Request Builder**
   - 도메인 인자를 받아 HTTP/gRPC 요청/메시지(경로, 헤더, 바디, gRPC Request)를 구성한다.
   - WorldService/Gateway/DAG Manager 별로 형식은 다르지만, 순수 함수 형태로 유지해 테스트를 단순화한다.
2. **Command (Transport + Breaker/Retry)**
   - Request Builder가 만든 요청을 실제로 전송하는 단일 커맨드 객체/함수.
   - circuit breaker, 재시도, health‑check backoff, 지연 측정 등은 이 레이어에서 처리한다.
   - 구현은 `qmtl/foundation/common.AsyncCircuitBreaker`, WorldService용 `BreakerRetryTransport` 등과 결합한다.
3. **Response Parser**
   - HTTP/gRPC 응답을 도메인 결과(예: `StrategyAck`, 큐맵 dict, 결정/활성 페이로드)로 변환한다.
   - 필요한 경우 스키마 검증(pydantic 등)과 기본값 채우기를 수행한다.
4. **Error Mapper**
   - 상태 코드/에러 코드/예외를 도메인 에러(예: `{"error": "duplicate strategy"}` 또는 전용 예외)로 변환한다.
   - 동일한 World/Gateway/DAG Manager 에러를 여러 어댑터에서 재사용할 수 있도록 공통 규칙을 정의한다.
5. **Facade**
   - SDK나 상위 서비스가 사용하는 퍼블릭 API 계층.
   - `WorldServiceClient.get_decide`, `DagManagerClient.diff`, `GatewayClient.post_strategy` 같은 메서드가 여기에 속한다.
   - Facade는 Request Builder/Command/Response Parser/Error Mapper를 조합하는 역할만 담당한다.

이 레이어 모델의 목적은 다음 두 가지다.

- radon CC 을 C → A/B 수준으로 낮추면서, 테스트 단위를 `Request Builder`, `Command`, `Parser`, `Error Mapper`, `Facade` 별로 좁혀 회귀 범위를 명확히 한다.
- Gateway/WorldService/DAG Manager 간에 재시도/에러 매핑/로깅 규칙을 공유해, 정책 변경 시 수정 범위를 줄인다.

## 3. 공통 모듈 스켈레톤

공통 Command/Parser/에러 결과 표현을 위해 `qmtl/foundation/common/rpc.py` 에 최소 스켈레톤을 도입한다.

```python
from dataclasses import dataclass
from typing import Any, Callable, Generic, Protocol, TypeVar

TResponse = TypeVar("TResponse")
TResult = TypeVar("TResult")

class RpcCommand(Protocol[TResponse]):
    async def execute(self) -> TResponse: ...

class RpcResponseParser(Protocol[TResponse, TResult]):
    def parse(self, response: TResponse) -> TResult: ...

@dataclass(slots=True)
class RpcError:
    message: str
    cause: Exception | None = None
    details: dict[str, Any] | None = None

@dataclass(slots=True)
class RpcOutcome(Generic[TResult]):
    result: TResult | None = None
    error: RpcError | None = None

    @property
    def ok(self) -> bool: ...

async def execute_rpc(
    command: RpcCommand[TResponse],
    parser: RpcResponseParser[TResponse, TResult],
    *,
    on_error: Callable[[Exception], RpcError] | None = None,
) -> RpcOutcome[TResult]: ...
```

특징:

- Command는 "요청 생성 + 전송"을 캡슐화하고, Parser는 "응답 → 도메인 결과"에만 집중한다.
- `execute_rpc` 는 Command/Parser 핸드쉐이크를 공통화해, Facade/어댑터 코드에서 try/except 블록 중복을 줄인다.
- retry/breaker/메트릭은 여전히 World/Gateway/DAG Manager 각 어댑터의 책임으로 남기고, 추후 필요 시 별도 공통 모듈로 확장한다.

이 스켈레톤은 이후 서브 이슈에서 다음과 같이 사용된다.

- WorldService: `get_decide` 의 HTTP 호출 부분을 `RpcCommand[httpx.Response]` 로 캡슐화하고, TTL/캐시 여부를 결정하는 Parser로 분리.
- DAG Manager: diff/tag 쿼리 호출을 Command 로 감싸고, CRC 검증/큐맵 정규화/네임스페이스 적용을 Parser/전략 객체로 이동.
- Gateway SDK: `GatewayClient.post_strategy` 응답 파싱 로직은 이미 헬퍼로 분해되어 있으며, 필요 시 Parser 형태로 래핑.

## 4. Command/Facade 적용 가이드

### 4.1 WorldServiceClient.get_decide (서브 이슈 #1583)

대상: `qmtl/services/gateway/world_client.py:WorldServiceClient.get_decide`

- **Request Builder**: `world_id` 와 헤더를 받아 `/worlds/{world_id}/decide` 경로와 쿼리/헤더를 구성.
- **Command**: `_transport.request("GET", url, headers=headers)` 호출을 `RpcCommand[httpx.Response]` 구현으로 캡슐화.
- **Response Parser**:
  - `Cache-Control` 헤더 기반 TTL 파싱.
  - envelope `ttl` 필드 파싱 및 잘못된 형식 처리.
  - `augment_decision_payload` 적용.
- **Error Mapper**:
  - 네트워크 예외/5xx 시 캐시 폴백 정책(`TTLCache`)을 명시적으로 정의.
  - 캐시 미존재 시 예외를 전파하거나 도메인 에러로 변환.
- **Facade**(`get_decide`):
  - 캐시 조회 → Command/Parser 실행 → 캐시 갱신/폴백 → `(payload, stale)` 튜플 반환.

### 4.2 DAG diff 경로 (서브 이슈 #1584)

대상: `DagManagerClient.diff` → `DiffExecutor.run` → `StrategyWorker._diff_strategy`.

- **Request Builder**: `DiffNamespace` 와 `DiffRequest` 생성 로직을 그대로 유지하되, `DiffStreamClient` 호출 인자를 명확히 분리.
- **Command**:
  - `DiffStreamClient.collect` 호출을 감싸는 `RpcCommand[dagmanager_pb2.DiffChunk]` 구현.
  - circuit breaker 및 `_collect_with_retries` 에서의 재시도/health 체크를 Command 내 책임으로 정리.
- **Response Parser / 전략**:
  - `DiffExecutor` 의 `DiffRunStrategy` (`QueueMapAggregationStrategy`, `SingleWorldStrategy`) 는 CRC 검증/센티넬/큐맵 정규화를 담당하는 고수준 Parser 역할.
- **Facade**:
  - `StrategyWorker._diff_strategy` 는 Command 실행과 실패 시 에러 기록/알람 전송/상태 전이만 담당.

## 5. 마이그레이션 전략 및 완료 조건

### 5.1 단계별 마이그레이션

1. **공통 스켈레톤 도입 (이 이슈 #1581)**
   - `qmtl/foundation/common/rpc.py` 에 Command/Parser/Outcome 타입과 `execute_rpc` 헬퍼를 추가한다.
   - 단위 테스트: `tests/qmtl/foundation/common/test_rpc.py` 에서 기본 성공/실패 경로를 검증한다.
2. **대표 경로 PoC (#1582, #1583)**
   - Gateway SDK: `GatewayClient.post_strategy` 경로의 응답 파싱/에러 매핑을 헬퍼/Parser 기반으로 정리(이미 #1582 에서 CC 개선).
   - WorldService: `get_decide` 를 Command/Parser 구조로 리팩터링하고, TTL/캐시 정책을 명확히 문서화 및 테스트.
3. **DAG diff 경로 정리 (#1584)**
   - DAG Manager diff 실행/재시도/CRC 검증/큐맵 정규화를 명확히 분리하고, `DiffRunStrategy` 를 Parser/전략 객체로 보는 방향으로 단순화.
4. **추가 RPC 어댑터로 확장**
   - Rebalancing, ControlBus Consumer, Strategy Submission 등에서 동일 패턴을 점진적으로 적용.

### 5.2 완료 기준

- Command/Facade/Parser/Error Mapper 역할이 이 문서 기준으로 정의되고, representative 경로(WorldService, DAG diff, Gateway SDK)에 대한 서브 이슈가 생성되어 있다.
- `qmtl/foundation/common/rpc.py` 가 머지되고, 최소한 하나 이상의 경로(#1582, #1583, #1584 중 하나 이상)에서 이 스켈레톤을 직접 또는 간접적으로 활용한다.
- radon CC 기준으로 RPC 어댑터 경로의 C 등급 함수 수가 감소하거나, C 등급이더라도 책임이 명확히 분리되었음을 이슈/PR 설명에서 근거로 제시한다.

## 6. 체크리스트

- [x] radon CC 리포트 기준 RPC 어댑터 관련 C 등급 함수 목록 수집.
- [x] Command/Facade/Parser/Error Mapper 레이어 모델 정의.
- [x] 공통 스켈레톤 모듈(`qmtl/foundation/common/rpc.py`) 도입 및 단위 테스트 추가.
- [ ] WorldService/SDK/DAG diff 대표 경로에서 Command/Facade 패턴 적용(#1582, #1583, #1584).

관련 이슈
- #1554
- #1581
- #1582
- #1583
- #1584

## 7. 워크플로 오케스트레이션 라돈 기록(유지보수 문서에서 이전)

워크플로 오케스트레이션 라돈 계획을 아키텍처 가이드 안으로 편입해 단일 기준점을 유지한다. 기존 Control-Plane/Runtime SDK 라돈 계획 문서는 상태를 반영한 뒤 폐기되었다.

### 7.1 범위
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

### 7.2 기본 radon 스냅샷 (계획 수립 시점)

다음 함수들은 radon CC 기준 C/D 급 복잡도를 보이면서, DAG Diff·토픽 오케스트레이션·전략 제출·Runtime SDK 오케스트레이션의 핵심 경로를 형성했다.

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

### 7.3 결과 요약 (2025-11-16 기준)

#1563–#1567 반영 후, 위 경로들의 CC 등급은 다음과 같이 개선되었다.

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

여전히 C 급 복잡도를 갖는 함수가 일부 존재하지만, 이 섹션은 위 오케스트레이션 경로에 한정된다. 2025-12-02 라돈 재측정에서 정규화·백필 경로가 A/B 등급으로 정리되어 별도 라돈 계획 문서는 종료했으며, 회귀가 보이면 정규화·백필 라돈 커맨드를 직접 재실행해 추적한다. WorldService 스키마/alpha 경로는 #1514 작업 완료로 `architecture/worldservice.md`와 `world/rebalancing.md`에 흡수되어 별도 radon 계획을 종료했다.

### 7.4 공통 불량 패턴

정비 전 오케스트레이션 경로에는 다음과 같은 공통 불량 패턴이 반복되었다.

- 단일 메서드에 **검증 → 외부 호출 → 재시도/백오프 → 결과 병합 → 예외 처리 → 메트릭/로그 방출**이 모두 포함되어 radon CC 가 자연스럽게 C/D 로 상승.
- 네트워크/브로커/WorldService 오류 처리와 다운그레이드 정책이 중첩된 `if`/`try` 블록으로만 표현되어, happy-path 를 읽기 어렵고 테스트 단위도 커짐.
- 재시도 정책, 로깅 포맷, 에러 매핑이 여러 모듈에서 중복 구현되어, 변경 시 동기화 비용이 큼.
- 성공/부분 성공/실패가 bool 플래그, `None` 반환, 예외, dict 기반 에러 메시지가 혼용된 형태로 표현되어 호출자 계층에서 분기 규칙이 일관되지 않음.

### 7.5 적용 패턴 / 설계 방향

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
  - Diff 실패 → TagQuery fallback, CRC sentinel fallback, WorldService stale/unavailable 시 compute 컨텍스트 다운그레이드 등은 Result 타입과 전용 메서드로 표현해, 정책이 코드 상에서 명확히 드러나도록 했다.

### 7.6 검증 체크리스트

- radon 복잡도/MI 확인
  - `uv run --with radon -m radon cc -s qmtl/services/dagmanager/diff_service.py qmtl/services/dagmanager/kafka_admin.py`
  - `uv run --with radon -m radon cc -s qmtl/services/gateway/strategy_submission.py qmtl/services/gateway/dagmanager_client.py qmtl/services/gateway/worker.py`
  - `uv run --with radon -m radon cc -s qmtl/runtime/sdk/gateway_client.py qmtl/runtime/sdk/tag_manager_service.py qmtl/runtime/sdk/backfill_engine.py qmtl/runtime/sdk/activation_manager.py`
  - 필요 시 전체 스냅샷: `uv run --with radon -m radon cc -s -n C qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- 회귀 테스트
  - `uv run -m pytest -W error -n auto qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- 문서 빌드
  - `uv run mkdocs build`

위 체크리스트와 서브 이슈들을 기준으로, #1549 에서 합의한 워크플로 오케스트레이션 복잡도 정리는 완료된 것으로 간주한다.

### 7.7 RPC 어댑터 계획(#1554, #1584)과의 연계

- DAG diff 실행 경로(`DagManagerClient.diff` → `DiffExecutor.run` → `StrategyWorker._diff_strategy`)는 이미 위 패턴을 적용한 상태이며, radon 기준으로 A/B 등급을 유지한다.
- RPC 어댑터 Command/Facade 설계안(#1554, #1581, #1584)은 이 경로를 대표 사례로 간주하며, 본 문서에서 레이어링 내용을 확인할 수 있다.
- #1584 에서는 추가 코드 변경 없이, 본 섹션과 RPC 어댑터 설계 문서 간의 정렬 상태를 검증하고 메타 이슈(#1554)에서 diff 경로를 완료된 상태로 표시한다.

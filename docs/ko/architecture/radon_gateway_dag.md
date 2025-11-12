---
title: "Gateway/DAG 제어면 Radon 개선 계획"
tags: ["radon", "control-plane"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# Gateway/DAG 제어면 Radon 개선 계획

Gateway, DAG Manager, ControlBus 경로는 SDK와 WorldService 사이에서 가장 먼저 계약을 고정하는 제어면입니다. 2025‑11 기준 Radon 측정에서 다수의 C/D 구간이 관측되었고, 이는 제출 큐 지연·복잡한 장애 대응의 주 원인으로 분류되었습니다. 본 계획은 qmtl/services/gateway/* 와 qmtl/services/dagmanager/* 전반의 복잡도를 낮춰 A/B 등급을 회복하고, 이 경로를 기초로 한 후속 런타임(#1511)·WorldService(#1513) 개선이 안전하게 추진되도록 합니다.

## 진단 요약

| 영역 | 경로 | Radon | 관측 |
| --- | --- | --- | --- |
| Gateway Health | `gateway_health.get_health` {{ code_url('qmtl/services/gateway/gateway_health.py#L21') }} | D (25) | 상태 수집·downgrade 경로가 단일 코루틴에 뒤섞여 타임아웃 시 스택 덤프 자체가 복잡 |
| 제출 FSM | `StrategySubmissionHelper.process` {{ code_url('qmtl/services/gateway/strategy_submission.py#L64') }} | D (22) | DAG diff, TTL pruning, CommitLog fan‑out 가 뒤섞여 회귀 테스트 작성이 어려움 |
| ControlBus Bridge | `ControlBusConsumer._handle_message` {{ code_url('qmtl/services/gateway/controlbus_consumer.py#L221') }} | D (25) | 메시지 유형별 파싱·재시도·메트릭 로직이 하나로 묶여 MTTR↑ |
| DAG Diff 서비스 | `DiffServiceServicer.Diff` {{ code_url('qmtl/services/dagmanager/grpc_server.py#L103') }} | D (21) | gRPC 스트림 복구, 토픽 리졸브, node cache 조합이 하나의 핸들러에 집중 |
| Kafka Admin | `_KafkaAdminClient.list_topics` {{ code_url('qmtl/services/dagmanager/server.py#L112') }} | D (21) | AdminClient 커넥션·보안 파라미터·재시도 로직이 얽혀 신규 설정 추가 시 리스크 |
| Graph Repo | `MemoryNodeRepository.get_buffering_nodes` {{ code_url('qmtl/services/dagmanager/node_repository.py#L197') }} | C (12) | Sentinel/버퍼링 상태 판정이 조건문 중심으로 누적 |

## 목표

- Control-plane Python 함수별 CC 등급을 Gateway/DAG 핵심 경로에서 **A/B로 축소**, D 이상 구간 제거
- Health/Submission/ControlBus 경로에 **계약 테스트**를 추가해 SDK·WS와의 상호작용을 문서화
- DAG Manager gRPC 및 Kafka Admin 진입점에 **fail-fast instrumentation**(prometheus + structured log)을 도입
- Radon 기준선과 개선 후 점수를 문서화하고 `uv run --with radon -m radon cc -s qmtl/services/{gateway,dagmanager}` 로 회귀 검사

## 개선 트랙

### 1. 헬스·감시장치 경량화

- `get_health`를 **수집기 + 어댑터** 구조로 분리. Kafka/Redis/Neo4j 호출은 TimeLimiter를 거쳐 팬아웃하고, 상단 코루틴은 결과 합성만 담당하도록 하여 CC<10 달성.
- WorldService/SDK 게이트웨이 플래그를 health 응답에 포함하여 #1514에서 요구하는 MultiWorldRebalanceRequest 버전 게이트 상태를 노출.
- 배포마다 임시 토글 대신 설정 키(`gateway.rebalance_schema_version`, `gateway.alpha_metrics_capable`, 선택적 `gateway.compute_context_contract`)로 위 플래그를 관리한다.
- preflight: 단위 테스트에서 aiohttp mocking 없이 `GatewayHealthCollector`에 더미 콜렉터를 주입해 timeout 경로를 검증.

### 2. 제출 FSM 단계화

- `StrategySubmissionHelper.process`를 **세 단계**(payload 정규화 → DAG diff 호출 → CommitLog fan‑out)로 나누고, 단계별 async context manager를 도입해 재시도/메트릭을 각각 주입.
- Redis FSM 및 TTL 캐시 만료 로직은 별도 헬퍼(`SubmissionPersistencePlan`)로 이동. DAG Manager gRPC 오류 시 현재의 broad except 대신 세분화된 예외 매핑을 문서화.
- Contract 테스트: `tests/services/gateway/test_strategy_submission_contract.py`에 SDK 샘플 페이로드(단일/다중 월드)를 기록, `uv run -m pytest qmtl/services/gateway/tests` 로 검증.

### 3. ControlBus 브리지 리팩터링

- `_handle_message`를 메시지 타입별 전략 테이블로 치환하고, ① 파싱 ② 유효성 ③ side-effect(CommitLog, Redis, WS) 단계를 generator로 쪼갭니다.
- Offsets 관리와 backpressure는 `_broker_loop`에서 맡고 `_handle_message`는 pure 함수에 가깝게 유지하여 CC<10 달성.
- 새 관찰 항목: `gateway_controlbus_unparsed_total`, `gateway_controlbus_retry_total` 메트릭을 metrics.py에 추가.

### 4. DAG Manager Diff/Admin 정비

- `DiffServiceServicer.Diff`는 **resume/ack 관리**와 **diff 계산**을 분리합니다. `_GrpcStream`이 현재 숨은 상태를 많이 들고 있으므로, diff 계산기는 `DiffExecutionContext` 데이터 클래스로 이관.
- `_KafkaAdminClient.list_topics`는 AdminClient 연결/보안 구성을 별도 `_AdminSession`으로 분리하여 CLI·테스트에서 주입 가능하게 합니다.
- `MemoryNodeRepository.get_buffering_nodes`는 sentinel/버퍼링 상태를 predicate map 으로 분기하고, NodeCache snapshot을 명확히 나눠 조건을 평탄화합니다.

### 5. 문서·계약·테스트

- 새 구조를 `docs/ko/architecture/gateway.md` / `dag-manager.md`의 관련 섹션과 상호 참조; 본 문서는 고정된 계획의 출처 역할.
- Smoke: `uv run --with radon -m radon cc -s qmtl/services/gateway qmtl/services/dagmanager | rg ' [CD]'` 로 회귀 감시.
- 회귀 테스트: `uv run -m pytest -W error -n auto tests/services/gateway tests/services/dagmanager`.

## 일정 및 산출물

| 단계 | 기간 | 산출물 |
| --- | --- | --- |
| Phase 0 (준비) | 1일 | Radon 기준선 스냅샷(.artifacts/radon_control_plane.json), health/submit 현재 계약 스냅샷 |
| Phase 1 (Gateway) | 3일 | 새 HealthCollector, Submission pipeline 모듈, 컨트랙트 테스트, grafana 경보 조정 |
| Phase 2 (ControlBus + DAG Diff) | 3일 | ControlBus 전략 테이블, DiffExecutionContext, Kafka Admin 세션, admin CLI 문서 업데이트 |
| Phase 3 (Regression) | 2일 | 통합 벤치(1k req/s 힙 캡), `uv run mkdocs build` 결과, 문서/레퍼런스 갱신 |

## 관련 의존성

- SDK 런타임(#1511) 계획에서 정의하는 `alpha_performance` 메트릭 키와 파서 보호 로직을 health 응답/큐 메타에 반영해야 합니다.
- WorldService(#1513)에서 추가될 `MultiWorldRebalanceRequest` v2 스키마 전환은 Gateway가 먼저 게이트 플래그를 제공해야 하므로, Phase 1 deliverable 에 포함합니다.
- Issue #1514의 공유 체크리스트(WS Schema Note, Gateway Compatibility Flag, SDK Parser Update)는 Phase 2 종료 전에 모두 ✅ 상태여야 합니다.

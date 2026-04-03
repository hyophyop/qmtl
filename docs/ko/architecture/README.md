---
title: "아키텍처"
tags:
  - architecture
  - overview
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 아키텍처

!!! abstract "요약"
    QMTL 아키텍처 구성 요소를 한눈에 볼 수 있는 허브입니다. 아래 링크를 통해 각 모듈의 세부 설계를 살펴보세요.

핵심 QMTL 구성 요소에 대한 설계 문서를 모아둔 곳입니다.

관련 용어는 [아키텍처 용어집](../architecture/glossary.md)에서 DecisionEnvelope, ActivationEnvelope, ControlBus,
EventStreamDescriptor와 같은 표준 명칭을 확인할 수 있습니다.

## 문서 지도

인접 계층:

- [제품 계약](../contracts/README.md): 전략 작성자와 상위 클라이언트가 알아야 하는 최소 표면 계약.
- [운영 문서](../operations/README.md): 승인, 배포, 관측, 롤백 등 운영 절차.

### Overview
- [아키텍처 개요](architecture.md): 시스템 상위 설계와 Core Loop 정렬.
- [아키텍처 예시](architecture_examples.md): 규범 문서에서 분리한 전략/데이터 on-ramp 예시.
- [아키텍처 용어집](glossary.md): DecisionEnvelope, ExecutionDomain 등 표준 용어.

### Design foundations
- [QMTL 문서 체계와 계층 분리](documentation_system.md): 규범, 제품 계약, 운영, 구현 상태를 분리하기 위한 문서 정보 구조.
- [QMTL 설계 원칙](design_principles.md): 기능 추가와 변경 시 따라야 할 1급 규칙.
- [QMTL Capability Map](capability_map.md): archetype이 아닌 capability 중심 구조.
- [QMTL Semantic Types](semantic_types.md): legality와 격리 규칙을 위한 의미론적 타입.
- [QMTL Decision Algebra](decision_algebra.md): 공통 decision family와 planner 경계.
- [QMTL 구현 추적성](implementation_traceability.md): 규범 문서와 현재 코드/테스트 근거의 매핑.

### Control plane
- [Gateway](gateway.md): 외부 단일 진입점, 프록시/캐시/스트림 중계.
- [DAG Manager](dag-manager.md): 그래프/노드/큐 SSOT, Diff 및 큐 오케스트레이션.
- [WorldService](worldservice.md): 월드 정책, 결정, 활성화, WVG SSOT.
- [월드 할당 및 리밸런싱 계약](rebalancing_contract.md): 할당/리밸런싱 제어면의 별도 규범 계약.
- [ControlBus](controlbus.md): 내부 제어 이벤트 패브릭(Activation/Queue/Policy).
- [월드 이벤트 스트림 런타임](world_eventstream_runtime.md): Gateway 경유 activation/queue/policy fan-out 경계.

### Data plane
- [심리스 데이터 프로바이더 v2](seamless_data_provider_v2.md): 데이터 정합성·백필·SLA·관측.
- [CCXT × Seamless 통합](ccxt-seamless-integrated.md): CCXT 기반 히스토리/라이브를 Seamless로 제공.

### Execution & brokerage
- [거래소 노드 세트](exchange_node_sets.md): 실행 레이어 구성(블랙박스 노드 세트).
- [실행 레이어 노드](execution_nodes.md): 프리트레이드/사이징/실행/체결/리스크/타이밍 노드.
- [실행 상태 머신과 TIF 정책](execution_state.md): 주문 상태 전이 및 TIF 의미론.
- [Lean Brokerage Model](lean_brokerage_model.md): 브로커리지 통합 세부 사항.

### Risk
- [Risk Signal Hub](risk_signal_hub.md): 포트폴리오/리스크 스냅샷 SSOT.

### Templates

### Engineering notes
- [SDK 레이어 가이드](../maintenance/engineering/sdk_layers.md): SDK 의존성 계층화 가이드.
- [심리스 데이터 프로바이더 모듈화 노트](../maintenance/engineering/seamless_data_provider_modularity.md): SDP 리팩터링/모듈 경계 노트.
- [RPC 어댑터 Command/Facade 설계안](../maintenance/engineering/rpc_adapters.md): RPC 어댑터 복잡도 저감 패턴.

### Reference appendices
- [아키텍처 런타임 신뢰성](../reference/architecture_runtime_reliability.md): determinism 체크리스트와 운영 신뢰성 보조 문서.

## 아키텍처 계층 한눈에 보기

QMTL 제어 플레인은 소수의 계층화된 서비스로 이루어져 있습니다. 각 계층은 하위 계층의 역할을 좁히고, 클라이언트와
운영자에게 명확한 계약을 제공합니다.

1. **Gateway** – SDK 및 자동화의 진입점. 클라이언트 요청을 정규화하고, 인증을 적용하며, 도메인 서비스로 라우팅합니다.
2. **DAG Manager** – 오케스트레이션 DAG의 기준 시스템. 버전 계획 저장소, 의존성 해석, 실행 큐잉, 토픽 네임스페이스 정책을
   책임집니다.
3. **WorldService** – 도메인 정책 실행. 월드 상태, 활성화 윈도우, 전략-월드 바인딩을 관리합니다.
4. **ControlBus** – Gateway, DAG Manager, 운영자 사이의 제어 신호를 전달하는 내부 이벤트 파이프라인입니다. SDK 소비자에게는
   일반적으로 비공개입니다.
5. **통합 계층** – 브로커리지, 거래소, 관측성 싱크에 대한 어댑터. 핵심 서비스를 수정하지 않고 기능을 확장합니다.

각 구성 요소의 심층 다이어그램은 위 링크된 문서에서 확인하세요.

## 운영 빠른 시작

서비스 기동과 설정 검증 절차는 운영 문서에 정리되어 있습니다. 실습이 필요하다면 아래 링크를 통해 단계별 안내를 따라가세요.

- [백엔드 빠른 시작](../operations/backend_quickstart.md#fast-start-validate-and-launch)
- [Operations Config CLI](../operations/config-cli.md)
- [Gateway 런타임 및 배포 프로필](../operations/gateway_runtime.md)
- [DAG Manager 런타임 및 배포 프로필](../operations/dag_manager_runtime.md)
- [ControlBus 운영 프로필 및 장애 대응](../operations/controlbus_operations.md)

{{ nav_links() }}

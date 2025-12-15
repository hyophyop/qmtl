---
title: "아키텍처"
tags:
  - architecture
  - overview
author: "QMTL 팀"
last_modified: 2025-12-15
---

{{ nav_links() }}

# 아키텍처

!!! abstract "요약"
    QMTL 아키텍처 구성 요소를 한눈에 볼 수 있는 허브입니다. 아래 링크를 통해 각 모듈의 세부 설계를 살펴보세요.

핵심 QMTL 구성 요소에 대한 설계 문서를 모아둔 곳입니다.

관련 용어는 [아키텍처 용어집](../architecture/glossary.md)에서 DecisionEnvelope, ActivationEnvelope, ControlBus,
EventStreamDescriptor와 같은 표준 명칭을 확인할 수 있습니다.

## 문서 지도

### Overview
- [아키텍처 개요](architecture.md): 시스템 상위 설계와 Core Loop 정렬.
- [아키텍처 용어집](glossary.md): DecisionEnvelope, ExecutionDomain 등 표준 용어.

### Control plane
- [Gateway](gateway.md): 외부 단일 진입점, 프록시/캐시/스트림 중계.
- [DAG Manager](dag-manager.md): 그래프/노드/큐 SSOT, Diff 및 큐 오케스트레이션.
- [WorldService](worldservice.md): 월드 정책, 결정, 활성화, 할당/리밸런싱.
- [ControlBus](controlbus.md): 내부 제어 이벤트 패브릭(Activation/Queue/Policy).

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
- [레이어드 템플릿 시스템](layered_template_system.md): 프로젝트/템플릿을 레이어로 조립하는 아키텍처.

### Engineering notes
- [SDK 레이어 가이드](../maintenance/engineering/sdk_layers.md): SDK 의존성 계층화 가이드.
- [심리스 데이터 프로바이더 모듈화 노트](../maintenance/engineering/seamless_data_provider_modularity.md): SDP 리팩터링/모듈 경계 노트.
- [RPC 어댑터 Command/Facade 설계안](../maintenance/engineering/rpc_adapters.md): RPC 어댑터 복잡도 저감 패턴.

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

{{ nav_links() }}

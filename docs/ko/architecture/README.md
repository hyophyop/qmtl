---
title: "아키텍처"
tags:
  - architecture
  - overview
author: "QMTL 팀"
last_modified: 2025-09-12
---

{{ nav_links() }}

# 아키텍처

!!! abstract "요약"
    QMTL 아키텍처 구성 요소를 한눈에 볼 수 있는 허브입니다. 아래 링크를 통해 각 모듈의 세부 설계를 살펴보세요.

핵심 QMTL 구성 요소에 대한 설계 문서를 모아둔 곳입니다.

관련 용어는 [아키텍처 용어집](../architecture/glossary.md)에서 DecisionEnvelope, ActivationEnvelope, ControlBus,
EventStreamDescriptor와 같은 표준 명칭을 확인할 수 있습니다.

## 연관 문서
- [아키텍처 개요](architecture.md): 시스템 상위 설계.
- [Gateway](gateway.md): 게이트웨이 구성 요소 명세.
- [DAG Manager](dag-manager.md): DAG 매니저 설계.
- [WorldService](worldservice.md): 월드 정책, 결정, 활성화.
- [ControlBus](controlbus.md): SDK에서는 보이지 않는 내부 제어 버스.
- [Lean Brokerage Model](lean_brokerage_model.md): 브로커리지 통합 세부 사항.

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

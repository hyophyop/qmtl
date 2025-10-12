---
title: "Architecture"
tags:
  - architecture
  - overview
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Architecture

!!! abstract "TL;DR"
    High-level hub for QMTL's architectural components. Use the links below to explore each module.

Design documents describing core QMTL components.

See also: Architecture Glossary (architecture/glossary.md) for canonical terms such as DecisionEnvelope, ActivationEnvelope, ControlBus, and EventStreamDescriptor.

## 관련 문서
- [Architecture Overview](architecture.md): High-level system design.
- [Gateway](gateway.md): Gateway component specification.
- [DAG Manager](dag-manager.md): DAG Manager design.
- [WorldService](worldservice.md): World policy, decisions, activation.
- [ControlBus](controlbus.md): Internal control bus (opaque to SDK).
- [Lean Brokerage Model](lean_brokerage_model.md): Brokerage integration details.

## 빠른 시작: 설정 검증 → 환경 등록 → 서비스 기동

아키텍처 전반을 이해하기 전에 구성 파일을 검증하고 서비스를 띄워보면 흐름을
빠르게 익힐 수 있다. 아래 순서는 [Operations/Config CLI](../operations/config-cli.md)
와 [Backend Quickstart](../operations/backend_quickstart.md)를 요약한 것이다.

1. `uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline`
   으로 게이트웨이/다그매니저 설정을 검증한다. 오류가 발생하면 아키텍처 설계
   문서를 참고해 빠진 요소를 보완한다.
2. 동일한 파일을 서비스 실행 시 `--config qmtl/examples/qmtl.yml` 로 넘기거나,
   자주 실행한다면 작업 디렉터리에 `cp qmtl/examples/qmtl.yml ./qmtl.yml`로 복사해
   자동 감지를 활용한다.
3. `qmtl service gateway --config qmtl/examples/qmtl.yml` 와 `qmtl service dagmanager server --config qmtl/examples/qmtl.yml`
   를 실행한다. 로그에 경고가 나오면 아키텍처 상 의존하는 외부 리소스를 점검한다.

{{ nav_links() }}

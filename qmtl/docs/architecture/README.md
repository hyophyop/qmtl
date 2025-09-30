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
2. `uv run qmtl config env export ... > .env.qmtl` 뒤 `source .env.qmtl` 로 환경 변수를
   등록하고 `export QMTL_CONFIG_FILE=$PWD/qmtl/examples/qmtl.yml` 을 추가해 서비스가
   동일한 YAML을 참조하도록 한다.
3. `qmtl service gateway` 와 `qmtl service dagmanager server` 를 실행하면
   환경 변수 폴백이 적용되어 별도의 `--config` 없이도 기동된다. 로그에
   경고가 나오면 아키텍처 상 의존하는 외부 리소스를 점검한다.

{{ nav_links() }}

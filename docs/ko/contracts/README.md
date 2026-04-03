---
title: "제품 계약"
tags:
  - contracts
  - architecture
  - product
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 제품 계약

## 목적

이 섹션은 QMTL의 사용자 및 상위 클라이언트가 알아야 하는 **최소 표면 계약**을 설명한다.

여기서는 다음 질문에 답한다.

- 전략 작성자나 SDK 사용자는 무엇만 알면 되는가?
- 어떤 표면이 읽기 전용이고, 어떤 지점부터 운영 승인/감사가 필요한가?
- Core Loop는 제품 관점에서 어디까지를 자동화로 약속하는가?

규범적 서비스 경계와 내부 SSOT는 [아키텍처](../architecture/README.md)에서 다루고,
운영 절차와 승인 플로우는 [운영 문서](../operations/README.md)에서 다룬다.

## 문서 지도

- [Core Loop 계약](core_loop.md): 전략 작성자 관점의 단일 제출 경로와 결과 계약.
- [월드 라이프사이클 계약](world_lifecycle.md): backtest → paper → live 전이와 운영 handoff 경계.

## 독자

- 전략 작성자
- SDK/CLI 소비자
- 제품 표면을 검토하는 리뷰어

## 비목표

- 내부 구현 클래스나 서비스 간 세부 프로토콜 설명
- 배포/승인/롤백 runbook
- 현재 구현 상태의 상세 추적

{{ nav_links() }}

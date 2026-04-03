---
title: "Core Loop 계약"
tags:
  - contracts
  - core-loop
  - product
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Core Loop 계약

## 관련 문서

- [제품 계약 개요](README.md)
- [월드 라이프사이클 계약](world_lifecycle.md)
- [아키텍처 개요](../architecture/architecture.md)
- [Gateway](../architecture/gateway.md)
- [WorldService](../architecture/worldservice.md)

## 요약

Concept ID: `CONTRACT-CORE-LOOP-GOLDEN-PATH`

QMTL의 전략 작성자 관점 Core Loop는 다음 한 줄로 요약된다.

> 전략 작성 → `Runner.submit(..., world=...)` → 결과 확인 → 전략 개선

이 계약에서 사용자가 기대할 수 있는 것은 다음과 같다.

- 제출 진입점은 `Runner.submit(..., world=...)` 하나다.
- 데이터 온램프, replay/backtest, 평가 요청, WorldService 결과 표면화는 시스템이 처리한다.
- 결과에서 권위 있는 결정은 WorldService가 제공한다.
- live 승격, allocation 적용, 승인/감사는 별도 운영 단계로 남는다.

## 계약 범위

이 문서는 **제품 표면 계약**만 정의한다.

- 포함:
  - 단일 제출 진입점
  - 제출 후 사용자에게 노출되는 결과 의미
  - 읽기 전용 관측과 운영 handoff 경계
- 제외:
  - 내부 서비스 간 호출 순서 세부
  - 운영 승인/롤백 절차
  - 현재 구현이 partial인지 여부

## Golden Path

### 1. 전략은 전략 로직만 표현한다

- 전략 작성자는 신호 생성과 필요한 데이터 요구를 정의한다.
- 데이터 공급/백필/시장 replay/월드 정책 평가는 시스템 레이어가 맡는다.

### 2. 제출은 단일 진입점으로 수렴한다

- 제출 표면은 `Runner.submit(..., world=...)`로 수렴한다.
- client-side `mode`는 계약상 노출하지 않는다.
- `world`는 필수 도메인 문맥이며, 단계(backtest/paper/live)는 월드 정책과 WorldService가 관리한다.

### 3. 결과는 “precheck + 권위 있는 world 결과”로 나뉜다

- 로컬 precheck는 참고 정보다.
- 권위 있는 상태, 가중치, 활성 여부, world 수준 결과는 WorldService 기준으로 읽는다.
- 결과가 불명확하거나 stale하면 시스템은 safe mode로 강등된다.

### 4. 사용자는 개선 루프에 집중한다

- 제출 후 사용자는 월드 성과/기여도/사유를 보고 전략을 개선한다.
- 운영 적용이 필요한 단계는 별도 운영 플로우로 넘긴다.

## 입력 계약

### 필수 입력

- 전략
- `world`

### 선택적 전문가 입력

- `preset`
- `data_preset`
- `returns`
- `auto_returns`

이 값들은 제품 표면을 확장하는 **전문가용 override**이지, 기본 사용 경로의 필수 지식이 아니다.

## 결과 계약

제출 결과는 최소한 다음 구조를 갖는다.

- 전략의 precheck 결과
- WorldService 평가 결과
- decision/activation 관련 world 상태
- allocation snapshot 같은 읽기 전용 보조 문맥
- safe mode / downgraded 여부

핵심 원칙:

- precheck는 참고용이고, WorldService가 권위 있는 판단을 제공한다.
- allocation 정보는 관측용이며, 자동으로 적용되었다는 뜻은 아니다.
- live 진입은 제출 하나만으로 보장되지 않는다.

## 자동화의 경계

Core Loop 계약은 “모든 운영 행위가 자동”임을 약속하지 않는다.

자동으로 처리되는 것:

- 전략 제출
- 기본 데이터 온램프
- replay/backtest
- 정책 평가 요청
- 결과 surface 정리

운영 단계로 남는 것:

- live promotion 승인
- allocation/rebalancing 적용
- 롤백, 감사, 비상 차단

## 다음 문서

- 단계 전이와 승격 거버넌스는 [월드 라이프사이클 계약](world_lifecycle.md)에서 본다.
- 내부 서비스 책임과 SSOT는 [아키텍처 개요](../architecture/architecture.md)와 [WorldService](../architecture/worldservice.md)에서 본다.
- 운영 절차는 [월드 활성화 런북](../operations/activation.md)과 [리밸런싱 실행 어댑터](../operations/rebalancing_execution.md)에서 본다.

{{ nav_links() }}

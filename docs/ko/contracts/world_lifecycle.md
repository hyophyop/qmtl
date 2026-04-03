---
title: "월드 라이프사이클 계약"
tags:
  - contracts
  - core-loop
  - world
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 라이프사이클 계약

## 관련 문서

- [제품 계약 개요](README.md)
- [Core Loop 계약](core_loop.md)
- [Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스](../architecture/core_loop_world_automation.md)
- [WorldService](../architecture/worldservice.md)
- [월드 활성화 런북](../operations/activation.md)
- [World Validation 거버넌스](../operations/world_validation_governance.md)

## 요약

Concept ID: `CONTRACT-WORLD-LIFECYCLE`

월드 라이프사이클 계약은 “전략이 월드 안에서 어떻게 관찰되고 승격되는가”를 제품 관점에서 설명한다.

핵심 원칙:

- 단계 전이는 월드 정책과 WorldService가 결정한다.
- 호출자는 전략과 월드만 제출하고, 단계(backtest → paper → live)는 직접 지정하지 않는다.
- `campaign/tick`은 추천 액션을 주는 계약이며, 자체적으로 apply를 강제하지 않는다.
- live promotion과 capital apply는 감사 가능한 운영 단계로 남는다.

## 단계 모델

월드 라이프사이클은 제품 관점에서 다음 단계를 가진다.

- `backtest`
- `paper` 또는 `dryrun`
- `live`

사용자에게 중요한 사실은 다음 두 가지다.

- 단계는 client-side mode로 고르는 것이 아니라 월드 정책 결과로 정해진다.
- 불명확하거나 stale한 상태에서는 시스템이 더 공격적인 단계로 가지 않고 안전 쪽으로 강등된다.

## Evaluation Run 계약

월드는 전략의 평가/검증/승격 후보를 Evaluation Run 단위로 추적한다.

사용자 관점에서 기대할 수 있는 것:

- 동일 전략은 단계별 평가 이력이 run 단위로 추적된다.
- paper/live 관찰 단계에서도 메트릭 갱신이 가능하다.
- metrics가 전부 클라이언트에서 수동 조립되어야 하는 것은 아니다.

내부 소싱 우선순위와 보강 규칙은 [Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스](../architecture/core_loop_world_automation.md)에서 규범적으로 정의한다.

## Campaign Tick 계약

`POST /worlds/{id}/campaign/tick`은 제품 관점에서 “다음 액션 추천” 표면이다.

이 엔드포인트는 다음을 약속한다.

- 현재 phase와 관찰 상태를 읽어 추천 액션을 계산한다.
- 추천 액션에 `idempotency_key`, `suggested_run_id`, `suggested_body` 같은 실행 힌트를 담을 수 있다.
- 자체적으로 부작용을 발생시키지 않는다.

즉, `tick`은 **결정 추천**이지 **운영 실행**이 아니다.

## live 승격 거버넌스

live promotion은 제품 계약상 자동 판정이 아니라 **정책 + 운영 거버넌스**의 결합이다.

최소 계약:

- `allow_live=false`이면 live 승격은 열리지 않는다.
- 관찰 윈도우, 필수 메트릭, 리스크 스냅샷 조건이 충족되지 않으면 승격은 차단된다.
- `manual_approval`과 `auto_apply` 같은 운영 모드는 존재할 수 있지만, 관찰과 검증 단계를 생략하는 의미는 아니다.

## 읽기 전용 표면과 운영 표면

읽기 전용 표면:

- submit 결과의 decision/activation/allocation snapshot
- campaign status
- campaign tick 추천 액션

운영 표면:

- activation apply / override
- live promotion 승인
- allocation / rebalancing apply
- rollback / freeze / drain

제품 계약은 읽기 전용 표면과 기본 자동화를 정의하고,
운영 표면은 감사와 승인 규율 아래 별도로 다룬다.

## 다음 문서

- backend 계약과 metric sourcing 규칙은 [Core Loop × WorldService — 캠페인 자동화와 승격 거버넌스](../architecture/core_loop_world_automation.md)에서 본다.
- 운영 승인/롤백은 [월드 활성화 런북](../operations/activation.md)에서 본다.
- override 재검토와 거버넌스는 [World Validation 거버넌스](../operations/world_validation_governance.md)에서 본다.

{{ nav_links() }}

---
title: "운영"
tags:
  - operations
  - overview
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 운영

프로덕션 환경에서 QMTL을 운영하고 유지관리하는 방법을 다룹니다.

## 시작점

- [백엔드 퀵스타트](backend_quickstart.md): WS/GW/DM 로컬 기동과 기본 smoke 절차.
- [배포 경로 결정](deployment_path.md): Release 0.1 기준의 표준 배포 경로.
- [Config CLI](config-cli.md): 기동 전 설정 검증과 operator 실행 순서.

## 서비스 런타임

- [Gateway 런타임 및 배포 프로필](gateway_runtime.md): Gateway 의존성, fail-fast, 장애 대응.
- [DAG Manager 런타임 및 배포 프로필](dag_manager_runtime.md): Neo4j/Kafka/ControlBus 운영 조건.
- [ControlBus 운영 프로필 및 장애 대응](controlbus_operations.md): broker/topic, lag, ACK/gap 대응.
- [Risk Signal Hub 운영 런북](risk_signal_hub_runbook.md): snapshot freshness, token, offload, worker 운영.

## 보조 런북

- [Fill Replay 런북](fills_replay.md): replay 비공개 표면의 현재 제약.
- [WS 전용 복원력 및 복구](ws_resilience.md): WebSocket-only 경로의 재연결과 중복 방지.
- [Neo4j 스키마 초기화](neo4j_migration.md): 초기화 전용 커맨드와 인덱스 범위.

## 검증과 관측

- [E2E 테스트](e2e_testing.md): 종단 간 테스트 실무.
- [품질 게이트](quality_gates.md): 하드 게이트, report-only 신호, mutation pilot 범위 정책.
- [모니터링](monitoring.md): 관측성 및 메트릭 관리.
- [코어 루프 관측성 최소셋](observability_core_loop.md): 최소 대시보드/SLO 경계.
- [World Validation 운영 가시성](world_validation_observability.md): validation/promotion 관측 포인트.
- [Grafana 대시보드](dashboards/gc_dashboard.json): 예시 메트릭 대시보드.

## 제어면과 승인 절차

- [월드 활성화 런북](activation.md): freeze/drain/switch/unfreeze 절차.
- [리밸런싱 실행 어댑터](rebalancing_execution.md): plan/apply 이후 주문 변환과 실행 경계.
- [World Validation 거버넌스](world_validation_governance.md): override와 재검토 절차.
- [ControlBus/큐 운영 표준](controlbus_queue_standards.md): 토픽, consumer group, retry/DLQ 기준.
- [World Isolation Runtime Scope](world_isolation_runtime_scope.md): RBAC/write-scope 분리와 backtest/dryrun 경로 네임스페이스 점검.

## 배포와 변경 관리

- [카나리아 롤아웃](canary_rollout.md): 점진적 배포 전략.
- [리스크 관리](risk_management.md): 운영 리스크 통제.
- [타이밍 제어](timing_controls.md): 스케줄링 안전장치.

{{ nav_links() }}

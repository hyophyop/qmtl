---
title: "Gateway 런타임 및 배포 프로필"
tags: [operations, gateway, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Gateway 런타임 및 배포 프로필

## 관련 문서

- [Gateway](../architecture/gateway.md)
- [백엔드 퀵스타트](backend_quickstart.md)
- [Config CLI](config-cli.md)
- [ControlBus/큐 운영 표준](controlbus_queue_standards.md)
- [Risk Signal Hub 운영 런북](risk_signal_hub_runbook.md)

## 목적

이 문서는 Gateway의 dev/prod 런타임 요구사항, 기동 전 점검 항목, 장애 대응 포인트를 운영 관점에서 정리한다.

- 규범 API, compute context, 프록시 경계는 [Gateway](../architecture/gateway.md)에서 다룬다.
- 이 문서는 "어떤 설정이 있어야 뜨는가, 어떤 의존성이 빠지면 어떻게 강등/실패하는가"에 집중한다.

## 런타임 프로필

### `profile: dev`

- `gateway.redis_dsn`이 비어 있으면 인메모리 Redis shim을 허용한다.
- `gateway.controlbus_brokers` 또는 `gateway.controlbus_topics`가 비어 있으면 ControlBus consumer를 비활성화한다.
- `gateway.commitlog_bootstrap` 또는 `gateway.commitlog_topic`이 비어 있으면 Commit-Log writer/consumer를 비활성화한다.
- WorldService 프록시가 비활성화되거나 도달 불가하면 submit 경로는 safe fallback에 머문다.

### `profile: prod`

- 다음 항목은 fail-fast 대상이다.
  - `gateway.redis_dsn`
  - `gateway.database_backend=postgres` 와 `gateway.database_dsn`
  - `gateway.controlbus_brokers`, `gateway.controlbus_topics`
  - `gateway.commitlog_bootstrap`, `gateway.commitlog_topic`
- 필수 항목이 비어 있으면 `qmtl config validate`와 서비스 기동이 모두 실패해야 한다.
- prod에서는 dev용 인메모리 대체를 운영 모드로 간주하지 않는다.

## 기동 전 점검

1. `uv run qmtl config validate --config <path> --offline`
2. `gateway.worldservice_url` 과 `gateway.enable_worldservice_proxy` 확인
3. `gateway.events.secret` 확인
4. prod라면 Redis, Postgres, ControlBus, Commit-Log 연결성 확인
5. Risk Signal Hub를 쓰는 배포라면 `risk_hub` 토큰, inline/offload 기준, blob-store 설정을 점검

## 외부 의존성

- **WorldService**: decision/activation/allocation 프록시와 world binding upsert 경계
- **Redis**: ingest/FSM/cache 핫패스
- **Postgres**: prod persistence 경계
- **ControlBus**: activation/policy/queue fan-out 입력
- **Commit-Log**: durable ingest/relay 추적
- **Risk Signal Hub**: Gateway는 생산자 역할만 수행하며, 소비는 WorldService/Exit Engine이 맡는다

## 장애 대응 체크리스트

- WorldService 미도달:
  - live 힌트를 신뢰하지 말고 safe mode 강등 여부를 먼저 확인
  - world proxy와 submit 후처리 로그를 본다
- Redis 누락:
  - prod에서는 기동 실패가 정상이다
  - dev에서는 의도치 않게 인메모리 대체로 떴는지 확인한다
- ControlBus lag 또는 consumer 비활성:
  - activation/state relay stale 여부를 먼저 확인
  - 토픽/consumer group 상태는 [ControlBus/큐 운영 표준](controlbus_queue_standards.md)도 함께 본다
- Commit-Log 비활성 또는 mismatch:
  - `gateway.commitlog_*` 설정과 직렬화 경고를 확인한다
- Risk Signal Hub push 실패:
  - Gateway는 producer이므로 재시도/backoff와 hub 토큰 오류를 먼저 점검하고, 후속 절차는 [Risk Signal Hub 운영 런북](risk_signal_hub_runbook.md)을 따른다

## 관측 포인트

- 서비스 헬스: `/status`
- Gateway 메트릭과 경보는 [모니터링 및 알림](monitoring.md)에서 본다.
- world status/allocation relay 문제는 [월드 활성화 런북](activation.md), [리밸런싱 실행 어댑터](rebalancing_execution.md)와 함께 본다.

{{ nav_links() }}

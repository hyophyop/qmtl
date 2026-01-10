---
title: "배포 경로 결정 (Release 0.1)"
tags: [deployment, release]
author: "QMTL Team"
last_modified: 2026-01-10
---

{{ nav_links() }}

# 배포 경로 결정 (Release 0.1)

Release 0.1의 **단일 배포 경로는 Docker/Compose**로 확정합니다. wheel 기반 배포는 개발/실험용으로만 남기고, 문서/템플릿/스모크 절차는 Compose 기준으로 통일합니다.

## 결정 요약

- **선택 경로:** Docker/Compose
- **배포 산출물:** `Dockerfile`, `docker-compose.yml`, `operations/docker-compose.qmtl.yml`
- **비선택 경로:** wheel 기반 직접 실행(공식 배포 절차로는 제공하지 않음)

## 필수 인프라 및 포트

Compose 스택이 요구하는 의존 인프라와 기본 포트는 아래와 같습니다.

| 구성 요소 | 목적 | 기본 포트 | Compose 서비스 |
| --- | --- | --- | --- |
| Redis | Gateway 캐시/세션 | 6379 | `redis` |
| Postgres | Gateway 영속 저장소 | 5432 | `postgres` |
| Neo4j | DAG Manager 그래프 저장소 | 7687/7474 | `neo4j` |
| Zookeeper | Kafka 메타데이터 | 2181 | `zookeeper` |
| Kafka | DAG 큐/이벤트 | 9092 | `kafka` |
| Gateway | 제출/상태 API | 8000 | `gateway` |
| DAG Manager | gRPC API | 50051 | `dagmanager` |

## 설정 및 시크릿

기본 구성 파일은 `operations/docker-compose.qmtl.yml` 입니다. 필요 시 운영 환경에 맞게 복사/오버라이드하세요.

필수 설정(Release 0.1 Compose 기준):

- `gateway.redis_dsn`
- `gateway.database_backend=postgres`
- `gateway.database_dsn`
- `dagmanager.neo4j_dsn`
- `dagmanager.kafka_dsn`

옵션/확장 설정(필요 기능을 활성화할 때만):

- `gateway.events.secret` (이벤트 서명)
- `gateway.commitlog_*`, `gateway.controlbus_*` (커밋 로그/ControlBus 연동)
- `worldservice.redis`, `worldservice.controlbus_*` (WorldService 추가 배포 시)

시크릿 값은 `.env` 또는 별도 시크릿 매니저로 관리하고, Compose 파일에는 평문으로 커밋하지 않습니다.

## 배포 절차 (Compose 기준)

1) 스택 기동

```bash
docker compose up -d
```

2) 상태 확인

```bash
docker compose ps
curl http://localhost:8000/status
```

3) 종료

```bash
docker compose down
```

## 최소 스모크 절차 (헬스 체크 + 기본 submit)

아래 절차는 “헬스 체크 + 기본 submit” 최소 확인을 보장합니다.

1) Gateway 헬스 체크

```bash
curl http://localhost:8000/status
```

2) 기본 submit (샘플 전략)

```bash
python -m qmtl.examples.general_strategy \
  --gateway-url http://localhost:8000 \
  --world-id demo
```

## 관련 문서/템플릿

- [백엔드 퀵스타트](backend_quickstart.md)
- [Docker & Compose](docker.md)
- Compose 예시:
  - `docker-compose.yml`
  - `tests/docker-compose.e2e.yml`
  - `qmtl/examples/templates/local_stack.example.yml`
  - `qmtl/examples/templates/backend_stack.example.yml`

{{ nav_links() }}

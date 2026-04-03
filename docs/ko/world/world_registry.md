---
title: "월드 레지스트리"
tags: [world, registry]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# 월드 레지스트리

본 문서는 전략 제출과 독립적으로 관리되는 월드 CRUD 및 전역 접근 계약을 정리합니다. 규범 API 엔벌로프는 [World API 레퍼런스](../reference/api_world.md), 정책/활성/결정의 SSOT는 [WorldService](../architecture/worldservice.md)에서 정의합니다.

## 1. 설계 원칙

- 월드 ID는 전역적으로 안정적인 slug여야 합니다.
- 레지스트리의 SSOT는 WorldService이며, Gateway는 외부 접근을 위한 프록시/캐시 역할만 수행합니다.
- 삭제는 기본적으로 소프트 삭제이며, 활성 세트가 남아 있으면 거부합니다.

## 2. 데이터 모델

- `worlds`
  - `world_id`, `name`, `description`, `owner`, `labels[]`
  - `created_at`, `updated_at`
  - `default_policy_version`, `state`
  - `allow_live`, `circuit_breaker`
- `world_policies`
  - `(world_id, version)`
  - `yaml`, `checksum`, `status`, `created_by`, `created_at`
- `world_activation`
  - Redis 키 `world:<id>:active`
- `world_audit_log`
  - `event`, `actor`, `request`, `result`, `created_at`

## 3. API 표면

- CRUD
  - `POST /worlds`
  - `GET /worlds`
  - `GET /worlds/{id}`
  - `PUT /worlds/{id}`
  - `DELETE /worlds/{id}`
- 정책 버전
  - `POST /worlds/{id}/policies`
  - `GET /worlds/{id}/policies`
  - `GET /worlds/{id}/policies/{v}`
  - `POST /worlds/{id}/set-default?v=V`
- 실행 경로
  - `GET /worlds/{id}/decide`
  - `GET /worlds/{id}/activation`
  - `POST /worlds/{id}/evaluate`
  - `POST /worlds/{id}/apply`
  - `GET /worlds/{id}/audit`

민감 엔드포인트(`apply`, activation override)는 world-scope RBAC가 필요합니다.

## 4. CLI 표면

```bash
qmtl world create --id crypto_mom_1h --file config/worlds/crypto_mom_1h.yml --set-default
qmtl world show crypto_mom_1h
qmtl world list --owner alice --state ACTIVE
qmtl world policy add crypto_mom_1h --file policy_v2.yml --version 2 --activate
qmtl world policy set-default crypto_mom_1h 2
qmtl world decide crypto_mom_1h --as-of 2025-08-28T09:00:00Z
qmtl world eval crypto_mom_1h
qmtl world apply crypto_mom_1h --plan plan.json --run-id $(uuidgen)
qmtl world delete crypto_mom_1h --force
```

## 5. 전역 접근과 일관성

- 서비스와 런너는 REST/WS를 통해 world 레지스트리를 읽습니다.
- 변경 API는 etag/resource_version을 요구해 낙관적 잠금을 적용합니다.
- 캐시 갱신은 `world.updated` 류 이벤트로 fan-out 합니다.

## 6. 운영 주의점

- 활성 전략 세트가 남아 있으면 삭제를 기본 거부합니다.
- 정책 롤백은 `set-default`로 처리하고, apply 실패 시 활성 스냅샷을 복원합니다.
- world 대시보드는 정책 버전, 활성 세트, 서킷 상태, 최근 알림을 보여야 합니다.

{{ nav_links() }}

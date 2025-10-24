---
title: "종단 간 테스트"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 종단 간 테스트

이 가이드는 필요한 서비스를 실행하고 E2E(종단 간) 테스트 스위트를 수행하는 방법을 설명합니다.

## 사전 준비물

다음 도구가 설치되어 있고 `PATH`에서 접근 가능한지 확인하세요:

- `docker`
- `uv`

## 의존성 설치

uv 환경을 생성하고 개발 요구 사항을 설치합니다:

```bash
uv venv
uv pip install -e .[dev]
```

## 스택 기동

Docker Compose로 모든 서비스를 시작합니다. DAG Manager와 Gateway는 저장소 루트의
`Dockerfile`로부터 빌드되며, `uv pip install .`로 QMTL을 설치하고 프로젝트 소스를
마운트하여 `qmtl` 엔트리포인트를 사용할 수 있게 합니다:

```bash
docker compose -f tests/docker-compose.e2e.yml up --build -d
```

이 명령은 Redis, Postgres, Neo4j, Kafka, Zookeeper와 함께 `qmtl service gateway`,
`qmtl service dagmanager server` 컨테이너를 기동합니다. Gateway는 포트 `8000`을
노출하며, DAG Manager gRPC 엔드포인트는 `50051`에서 접근 가능합니다.

## 테스트 실행

uv 환경에서 종단 간 테스트를 실행합니다:

```bash
uv run -m pytest -n auto tests/e2e
```

WorldService-우선 배선과 이벤트 구독을 간단히 검증하려면,
`tests/e2e/test_worldservice_smoke.py`의 스모크 테스트를 실행하세요:

```bash
uv run -m pytest -n auto tests/e2e/test_worldservice_smoke.py -q
```

테스트는 다음을 수행합니다:

- Gateway `/status` 엔드포인트 헬스 체크
- 서로 다른 두 `world_id`에 대해 `/events/subscribe`로 토큰 발급 및 JWT 클레임 확인
- 두 토큰 모두 `/ws/evt` WebSocket 핸드셰이크
- Gateway 프록시를 통해 월드별 전략 제출

이 테스트는 ControlBus나 실행 중인 WorldService가 없어도 동작합니다.

전체 테스트 스위트를 실행하려면:

```bash
uv run -m pytest -n auto -q tests

참고: 병렬 실행에는 `pytest-xdist`가 필요합니다. 설치되어 있지 않다면
`uv pip install pytest-xdist`로 추가하거나 dev extras에 포함하세요.
```

## 백필(Backfill)

라이브 처리가 시작되기 전에 과거 데이터를 로드하려면 전략 실행 시 백필을 시작합니다:

```bash
qmtl tools sdk run tests.sample_strategy:SampleStrategy \
       --start-time 1700000000 \
       --end-time 1700003600
```

전체 워크플로 개요는 [backfill.md](backfill.md)를 참고하세요.


{{ nav_links() }}

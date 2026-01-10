---
title: "Docker & Compose"
tags: [docker, compose]
author: "QMTL Team"
last_modified: 2026-01-10
---

{{ nav_links() }}

# Docker & Compose

이 문서는 QMTL에서 Docker를 어떻게 사용하고, 어떤 Compose 파일이 있으며, 로컬 개발/테스트 용도로 서비스를 기동하는 방법을 설명합니다.

Release 0.1의 공식 배포 경로는 Docker/Compose이며, 상세 절차는
[배포 경로 결정](deployment_path.md)을 따릅니다.

## 개요

- Docker는 로컬 인프라(Redis, Postgres, Neo4j, Zookeeper, Kafka)를 준비하고 QMTL 서비스(Gateway, DAG Manager)를 컨테이너로 실행하는 데 사용됩니다.
- Compose 파일은 목적에 따라 다르게 제공됩니다: 빠른 스모크 체크, 엔드 투 엔드(E2E) 테스트, 보다 풍부한 로컬 개발 스택.
- 리포지토리 최상위에는 Compose 빌드 시 서비스 컨테이너에서 사용하는 `Dockerfile` 이 포함되어 있습니다.

## Compose 파일

### 루트 스택: `docker-compose.yml`

- 목적: 인프라 + QMTL 서비스를 포함한 개발자 중심 로컬 스택
- 서비스: `redis`, `postgres`, `neo4j`, `zookeeper`, `kafka`, `dag-manager`, `gateway`
- 빌드: `dag-manager`, `gateway` 는 최상위 `Dockerfile` 로부터 빌드됩니다.
- 헬스 체크: 대부분의 서비스는 빠른 피드백을 위한 헬스 체크를 제공합니다.
- 예시:

```bash
docker compose up -d
docker compose ps
docker compose logs -f gateway
docker compose down
```

메모:
- 포트: 8000(Gateway), 50051/8001(DAG Manager), 5432(Postgres), 7687/7474(Neo4j), 9092(Kafka), 2181(Zookeeper), 6379(Redis)
- 볼륨: 영속성을 위해 명명된 볼륨(`postgres_data`, `neo4j_data` 등)을 사용합니다.

### 최소 테스트 스택: `tests/docker-compose.yml`

- 목적: CI/로컬에서 Docker 및 기본 네트워킹을 빠르게 점검
- 서비스: `zookeeper`, `kafka`(고정 `confluentinc` 이미지), HTTP를 서비스하는 플레이스홀더 `gateway`(`python:3.11-slim`)
- 사용처: `tests/project/test_docker_compose.py` 가 스택을 올렸다가 내립니다.
- 예시:

```bash
docker compose -f tests/docker-compose.yml up -d
docker compose -f tests/docker-compose.yml down
```

### E2E 스택: `tests/docker-compose.e2e.yml`

- 목적: 실제 인프라와 QMTL 서비스를 대상으로 엔드 투 엔드 테스트 스위트를 실행
- 서비스: `redis`, `postgres`, `neo4j`, `zookeeper`, `kafka`, 리포지토리 `Dockerfile` 로 빌드한 QMTL `gateway`, `dagmanager`
- 사용처: E2E 문서와 테스트(아래 참고). `tests/project/test_docker_compose_e2e.py` 에서 검증합니다.
- 예시:

```bash
docker compose -f tests/docker-compose.e2e.yml up --build -d
uv run -m pytest -n auto tests/e2e
docker compose -f tests/docker-compose.e2e.yml down
```

참고: [E2E 테스트](e2e_testing.md)

## Dockerfile

경로: `Dockerfile`

- 베이스: `python:3.11-slim`
- 설치: `uv` 와 QMTL 패키지를 `uv pip install .` 로 설치
- 사용처: `docker-compose.yml`, `tests/docker-compose.e2e.yml` 에서 서비스 빌드에 사용

빠른 빌드 예시:

```bash
docker build -t qmtl:dev .
```

## 자주 쓰는 명령

- 시작/종료: `docker compose up -d` / `docker compose down`
- 확인: `docker compose ps`, `docker compose logs -f <service>`
- 재빌드: `docker compose build --no-cache`
- 이미지 풀: `docker compose pull` (CI에서 빠른 시작에 유용)
- 프로젝트 분리: 이름 충돌을 피하려면 `COMPOSE_PROJECT_NAME=qmtl` 을 지정

## 문제 해결

- 포트 충돌: 8000, 50051, 5432, 7687, 7474, 9092, 2181, 6379 포트가 비어 있는지 확인하세요.
- Kafka 연결:
  - 최소 테스트 스택은 편의를 위해 `PLAINTEXT://localhost:9092` 를 광고합니다.
  - 루트 스택은 컨테이너 네트워크를 위해 `kafka:9092` 를 광고합니다.
- 오래된 볼륨: `docker compose down -v` 또는 `docker volume rm <name>` 으로 정리합니다.
- Apple Silicon: arm64 이미지를 제공하지 않는 경우 해당 서비스에 `platform: linux/amd64` 를 지정하세요(에뮬레이션으로 느릴 수 있음).
- Compose v2: 더 이상 사용되지 않는 `docker-compose` 대신 `docker compose` 를 사용하세요.

## Docker가 참조되는 위치

- Compose 파일:
  - `docker-compose.yml` (루트)
  - `tests/docker-compose.yml`
  - `tests/docker-compose.e2e.yml`
- 테스트:
  - `tests/project/test_docker_compose.py` (`docker` 미설치 시 스킵)
  - `tests/project/test_docker_compose_e2e.py` (예상 서비스 확인)
- 문서 및 README:
  - `README.md` (E2E 퀵스타트)
  - `docs/ko/operations/e2e_testing.md`
  - `docs/ko/architecture/dag-manager.md` (통합 메모)

## 관련 문서

- [E2E 테스트](e2e_testing.md)
- [DAG Manager](../architecture/dag-manager.md)

{{ nav_links() }}

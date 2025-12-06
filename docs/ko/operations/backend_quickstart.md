---
title: "백엔드 퀵스타트"
tags: [quickstart, gateway, dagmanager, worldservice]
author: "QMTL Team"
last_modified: 2025-09-23
---

{{ nav_links() }}

# 백엔드 퀵스타트 (WS + GW + DM)

이 퀵스타트는 로컬 개발을 위해 QMTL 핵심 백엔드 서비스를 빠르게 기동하는 절차를 안내합니다.

- WorldService (WS) – 월드, 정책, 결정, 활성화 관리
- Gateway (GW) – 클라이언트 API, WorldService 프록시, DAG Manager 인입
- DAG Manager (DM) – 전역 DAG SSOT, diff, 큐 오케스트레이션

추가로 [Docker & Compose](docker.md) 의 전체 스택 설명과 [E2E 테스트](e2e_testing.md) 문서를 참고하세요.

!!! tip "배포 프로필 체크"
    `profile: dev`(기본)에서는 redis/kafka/neo4j/commit-log가 비어 있어도 인메모리 대체 구현으로 기동됩니다. 운영 배포에서는 `profile: prod`를 지정하고, `gateway.redis_dsn`, `gateway.database_backend=postgres` + `gateway.database_dsn`, `gateway.controlbus_*`, `gateway.commitlog_*`, `dagmanager.neo4j_dsn`, `dagmanager.kafka_dsn`, `worldservice.server.redis`를 모두 채워야 `qmtl config validate`와 서비스 부팅이 성공합니다.

## 사전 준비

- uv로 관리하는 Python 환경: `uv venv && uv pip install -e .[dev]`
- 선택: 인프라 서비스를 위한 Docker/Compose

<a id="fast-start-validate-and-launch"></a>
## 빠른 검증 및 실행 루프

운영용 YAML이 준비되어 있다면 다음 순서로 검증하고 서비스를 실행하세요.

1. **정적 검증** – 서비스 부팅 전 구성을 확인합니다.

   ```bash
   uv run qmtl config validate --config <path-to-config> --offline
   ```

   기준 시작점으로 `qmtl/examples/qmtl.yml` 을 사용할 수 있습니다. 경로를 조정하거나 작업 디렉터리에 `qmtl.yml` 로 복사하면 서비스 명령이 자동으로 찾습니다.

2. **Gateway** – 검증한 설정으로 진입점을 실행합니다.

   ```bash
   qmtl service gateway --config <path-to-config>
   ```

3. **DAG Manager** – 동일한 설정으로 오케스트레이션 서비스를 시작합니다.

   ```bash
   qmtl service dagmanager server --config <path-to-config>
   ```

장기 실행 프로세스에서는 구성 파일을 작업 디렉터리의 `qmtl.yml` 로 복사해 명령이 자동으로 찾도록 하는 것이 좋습니다.

## 옵션 A — 로컬 실행(Docker 없음)

1) WorldService 시작(SQLite + Redis 예제)

```bash
cat > worldservice.yml <<'EOF'
worldservice:
  dsn: sqlite:///worlds.db
  redis: redis://localhost:6379/0
  bind:
    host: 0.0.0.0
    port: 8080
  auth:
    header: Authorization
    tokens: []
EOF
uv run uvicorn qmtl.services.worldservice.api:create_app --factory --host 0.0.0.0 --port 8080
```

명령을 실행하는 디렉터리에서 `worldservice.yml` 이 발견되도록 유지하세요.

2) Gateway 구성 및 시작

- `qmtl/examples/qmtl.yml` 수정:
  - `gateway.worldservice_url: http://localhost:8080`
  - `gateway.enable_worldservice_proxy: true`
  - `gateway.events.secret: <64자 헥사 시크릿 생성>`
  - `gateway.websocket.rate_limit_per_sec: 0` (무제한 유지)
- 구성으로 Gateway 실행:

```bash
qmtl service gateway --config qmtl/examples/qmtl.yml
```

3) 동일한 구성으로 DAG Manager 시작

```bash
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

메모
- 프로덕션 유사 토픽이 필요하다면 YAML에서 Kafka/Neo4j를 설정하세요. 미설정 시 DM은 인메모리 저장소와 큐를 사용합니다.
- 토픽 네임스페이스는 기본 활성입니다. 단순 로컬 테스트에서는 `dagmanager.enable_topic_namespace: false` 를 설정해 접두어를 비활성화할 수 있습니다.

## 옵션 B — Docker Compose

E2E 스택을 사용해 인프라 + 서비스를 동시에 실행할 수 있습니다.

> 표준 Compose 파일은 패키지 내
> {{ code_link('qmtl/examples/templates/local_stack.example.yml', text='`qmtl/examples/templates/local_stack.example.yml`') }}
> 과
> {{ code_link('qmtl/examples/templates/backend_stack.example.yml', text='`qmtl/examples/templates/backend_stack.example.yml`') }}
> 에 위치합니다. 기본 스택이 필요할 때 프로젝트에 복사해 사용하세요.

```bash
docker compose -f tests/docker-compose.e2e.yml up --build -d
# Gateway: http://localhost:8000, DAG Manager gRPC: 50051
```

또는 헬스 체크와 볼륨이 포함된 루트 스택:

```bash
docker compose up -d
# Gateway: http://localhost:8000, DAG Manager HTTP: http://localhost:8001/health
```

`docker compose down` (볼륨 삭제 시 `-v`) 으로 스택을 종료하세요.

## 검증

- Gateway 상태: `curl http://localhost:8000/status`
- DAG Manager HTTP 헬스(루트 스택): `curl http://localhost:8001/health`
- Neo4j 초기화(사용 중일 때):

```bash
qmtl service dagmanager neo4j-init \
  --uri bolt://localhost:7687 --user neo4j --password neo4j
```

## 전략 실행(Gateway + WorldService)

샘플 전략을 Gateway와 월드 ID를 지정해 실행합니다.

```bash
python -m qmtl.examples.general_strategy \
  --gateway-url http://localhost:8000 \
  --world-id demo
```

오프라인 실행(WS/GW 없음): `python -m qmtl.examples.general_strategy`.

## 문제 해결

- 포트 사용 중: 8000(GW), 50051/8001(DM), 6379(Redis), 7687/7474(Neo4j), 9092(Kafka)가 비어 있는지 확인하세요.
- WorldService 프록시 비활성화: Gateway는 실행되지만 SDK는 오프라인/백테스트 모드로 폴백합니다.
- Apple Silicon: arm64 이미지를 제공하지 않는 서비스에는 `platform: linux/amd64` 를 추가하세요.

{{ nav_links() }}

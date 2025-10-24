---
title: "Config CLI"
tags: [cli, config, operations]
author: "QMTL Team"
last_modified: 2025-10-12
---

{{ nav_links() }}

# Config CLI (검증 & 실행)

`qmtl config validate` 명령으로 Gateway와 DAG Manager 구성을 서비스 시작 전에 검증하세요. 이 명령은 통합 YAML을 읽고 필요한 섹션이 없거나 검증에서 `ERROR` 심각도가 발생하면 즉시 실패합니다.

## 구성 파일 검증

구성 파일을 대상으로 검증을 실행합니다. `--offline` 플래그를 사용하면 연결 검사를 건너뛰고 비활성화된 외부 서비스를 알려줍니다.

```bash
uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline
```

예시 출력:

```
gateway:
  redis         WARN   Offline mode: skipped Redis ping for redis://localhost:6379
  database      OK     SQLite ready at ./qmtl.db
  controlbus    OK     ControlBus disabled; no brokers/topics configured
  worldservice  OK     WorldService proxy disabled

dagmanager:
  neo4j       OK     Neo4j disabled; using memory repository
  kafka       OK     Kafka DSN not configured; using in-memory queue manager
  controlbus  OK     ControlBus disabled; no brokers/topics configured
```

경고는 건너뛴 검사나 폴백을 의미합니다. `ERROR` 가 하나라도 있으면 종료 코드 1로 종료되어 CI/CD에서 빠르게 실패를 감지할 수 있습니다. 요청한 섹션(예: `dagmanager`)이 구성에서 누락되면 CLI는 설명 메시지를 출력하고 어떤 검증도 실행하지 않은 채 종료 코드 2로 종료합니다.

## 실행 순서

서비스는 동일한 YAML을 직접 사용합니다. 경로를 명령줄로 넘기거나 `qmtl.yml` 로 복사해 상시 실행되는 데몬이 자동으로 찾도록 하세요.

```bash
# 먼저 검증합니다.
uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline

# 동일한 YAML로 서비스 실행.
qmtl service gateway --config qmtl/examples/qmtl.yml
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

구성 파일을 찾지 못하면 서비스는 경고를 로그에 남기고 내장 기본값으로 폴백하므로, 시작 시 잘못된 경로를 감지할 수 있습니다.

{{ nav_links() }}

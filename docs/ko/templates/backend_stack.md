---
title: "백엔드 스택 구성 템플릿"
tags: [templates, backend]
author: "QMTL Team"
last_modified: 2025-09-24
---

{{ nav_links() }}

# 백엔드 스택 구성 템플릿

프로덕션 지향의 Docker Compose 번들은 Gateway, DAG Manager, WorldService와
지원 인프라 전반을 구동합니다. 템플릿은
{{ code_link('qmtl/examples/templates/backend_stack.example.yml', text='`qmtl/examples/templates/backend_stack.example.yml`') }}에
있습니다. 전체 배포의 출발점이 필요할 때 이 파일을 복사한 뒤, 서비스 이미지, 자격 증명,
호스트명을 환경에 맞게 수정하세요.

## 서비스 구성

이 템플릿은 Redis, Postgres, Kafka, Neo4j, Prometheus/Grafana와 핵심 QMTL 서비스를
기동합니다. `docker compose` 실행 전에 다음 항목을 업데이트하세요:

- `x-qmtl-image:` 블록 – 사설 레지스트리 태깅 이미지로 교체
- `volumes:` – 영속 데이터(Postgres, Neo4j, Prometheus)의 호스트 경로 조정
- `environment:` – 플레이스홀더 시크릿/접속 정보를 실제 값으로 교체
- `depends_on:` – 운영하지 않을 서비스는 제거

## 사용 팁

1. 템플릿을 프로젝트로 복사합니다:

   ```bash
   cp $(python -c "import importlib.resources as r; print(r.files('qmtl.examples').joinpath('templates/backend_stack.example.yml'))") ./templates/backend_stack.yml
   ```

2. 복사한 파일을 수정하고 프로젝트 스캐폴딩과 함께 커밋합니다.
3. `docker compose -f templates/backend_stack.yml up -d`로 로컬 또는 CI에서 스택을 실행합니다.

{{ nav_links() }}

---
title: "로컬 스택 구성 템플릿"
tags: [templates, local]
author: "QMTL Team"
last_modified: 2025-09-24
---

{{ nav_links() }}

# 로컬 스택 구성 템플릿

경량 개발 환경에서는
{{ code_link('qmtl/examples/templates/local_stack.example.yml', text='`qmtl/examples/templates/local_stack.example.yml`') }}
을 사용하세요. 외부 의존성 없이 Gateway, DAG Manager, WorldService를 테스트할 수 있도록
최소 구성의 Redis, SQLite, 모의 메시징 서비스를 제공합니다.

## 커스터마이즈 체크리스트

- `QMTL_*` 환경 변수를 프로젝트 전용 데이터베이스와 토픽 접두사로 맞춥니다.
- 선택 서비스(Redis, Kafka shim)는 주석 처리하거나 포트를 조정해 로컬 충돌을 피하세요.
- 필요 시 Jaeger, Tempo 등의 도구를 compose 파일에 추가하세요.

## 빠른 복사 명령

```bash
python - <<'PY'
import importlib.resources as resources
path = resources.files('qmtl.examples').joinpath('templates/local_stack.example.yml')
print(path)
PY
```

출력된 경로를 `cp`에 전달해 워크스페이스로 템플릿을 복사하세요.

{{ nav_links() }}

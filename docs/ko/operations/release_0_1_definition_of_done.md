---
title: "Release 0.1 완료 기준(DoD)"
tags:
  - operations
  - release
  - definition-of-done
author: "QMTL Team"
last_modified: 2026-01-09
---

{{ nav_links() }}

# Release 0.1 완료 기준(DoD)

이 문서는 QMTL Release 0.1을 “완료”로 판정하기 위한 기준을 명문화합니다. 릴리스 판단은 아래 모든 조건을 만족할 때에만 가능합니다.

## 범위

### 포함

- Core Loop 자동화와 핵심 실행 흐름(Submit → Evaluate/Activate → Execution/Gating → 관찰) 기준 정의
- Gateway/WorldService/DAG Manager 기본 기동과 헬스 체크 확인
- 로컬/CI 검증 명령의 고정된 집합
- 릴리스 산출물 최소 요건

### 제외

- 전략(알파) 로직 자체의 성능 검증
- 운영 환경의 장기 안정성/확장성 튜닝
- 신규 외부 브로커/데이터 공급자 통합

## 필수 CLI/엔드포인트 표면

### CLI

아래 명령은 Release 0.1의 필수 표면입니다. 각 명령은 최소 한 번 실제 실행 가능한 상태여야 합니다.

- 구성 검증: `uv run qmtl config validate --config <path-to-config> --offline`
- Gateway 기동: `qmtl service gateway --config <path-to-config>`
- DAG Manager 기동: `qmtl service dagmanager server --config <path-to-config>`
- 예시 전략 실행(온라인): `python -m qmtl.examples.general_strategy --gateway-url http://localhost:8000 --world-id demo`

자세한 실행 순서는 [백엔드 퀵스타트](backend_quickstart.md)를 참고합니다.

### 엔드포인트

- Gateway 상태 확인: `GET /status`
- DAG Manager 헬스 확인(루트 스택 기준): `GET /health`

## 필수 테스트/검증 커맨드 (로컬/CI parity)

Release 0.1의 검증은 CI와 동일한 명령 집합을 로컬에서도 실행 가능해야 합니다.

```bash
uv run --with mypy -m mypy
uv run mkdocs build --strict
uv run python scripts/check_design_drift.py
uv run python scripts/lint_dsn_keys.py
uv run --with grimp python scripts/check_import_cycles.py --baseline scripts/import_cycles_baseline.json
uv run --with grimp python scripts/check_sdk_layers.py
uv run python scripts/check_docs_links.py
bash scripts/package_smoke.sh
uv run -m pytest --collect-only -q
PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1 -k 'not slow'
PYTHONPATH=qmtl/proto uv run pytest -p no:unraisableexception -W error -q tests
USE_INPROC_WS_STACK=1 WS_MODE=service uv run -m pytest -q tests/e2e/world_smoke -q
CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q
```

핵심 Core Loop 계약 테스트는 Core Loop 요약(아키텍처)과 테스트 스켈레톤을 기준으로 유지합니다.

- [Core Loop 요약](../architecture/architecture.md#core-loop-summary)
- 테스트 스켈레톤: `tests/e2e/core_loop/README.md`

## 릴리스 산출물 최소 요건

- `CHANGELOG.md`에 Release 0.1 변경 사항 반영
- 문서 빌드 성공: `uv run mkdocs build --strict`
- Python 패키지 산출물:
  - `uv pip wheel .`(또는 `uv build --wheel`)로 생성한 wheel
  - `python -m build` 또는 동등 절차로 생성한 sdist
- 패키징 산출물 설치 스모크(최소 `qmtl --help`)를 `scripts/package_smoke.sh`로 재현 가능해야 함
- 릴리스 문서 아카이빙 절차 확인: [릴리스 프로세스](release.md)

## 결정 근거

- Core Loop 요약 정의와 테스트 계약을 Release 0.1의 안정성 기준으로 채택합니다.
- 운영 기동 경로는 백엔드 퀵스타트에 맞춰 최소 구성으로 확인합니다.

{{ nav_links() }}

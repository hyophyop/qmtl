---
title: "Python 환경 가이드"
tags: [guide, python, environment]
author: "QMTL Team"
last_modified: 2025-08-21
---

# Python 환경 가이드

본 프로젝트는 개발 환경과 CI 간 일관성을 위해 Python 3.11과 `uv` 패키지 관리자를 표준으로 사용합니다.

- 요구 버전: Python >= 3.11
- 관리자: `uv` (빠르고 재현 가능한 Python/의존성 관리)

## 퀵스타트

```bash
# 프로젝트용으로 Python 3.11 설치 및 고정
uv python install 3.11
uv python pin 3.11

# 개발 의존성을 editable 모드로 설치
uv pip install -e .[dev]

# 고정된 인터프리터로 병렬 테스트 실행
uv run -m pytest -W error -n auto
```

## 참고 사항

- `pyproject.toml`에는 `requires-python = ">=3.11"`이 명시되어 있습니다.
- 테스트나 도구 실행 시 `uv run`을 사용해 고정된 인터프리터를 일관되게 활용하세요.
- 빠른 피드백을 위해 테스트는 병렬(`-n auto`)로 실행하세요. `pytest-xdist`가 없다면 `uv pip install pytest-xdist`로 설치합니다.
- CI 역시 Python 3.11을 사용해 환경 편차를 최소화해야 합니다.

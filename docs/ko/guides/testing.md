---
title: "테스트 & Pytest 규칙"
tags:
  - guide
  - testing
  - pytest
author: "QMTL Team"
last_modified: 2025-09-08
---

# 테스트 & Pytest 규칙

이 가이드는 QMTL에서 pytest를 사용할 때 테스트를 구성하고 빠르게 실행하며, 흔한 함정을 피하는 방법을 정리합니다.

## Python & 환경

- Python과 의존성 관리는 `uv`를 사용합니다.
- 프로젝트 Python 버전은 `>=3.11`입니다. 로컬에서도 고정하세요.
  - `uv python install 3.11`
  - `uv python pin 3.11`
  - `uv pip install -e .[dev]`

## 빠른 프리플라이트(행 감지)

전체 스위트 전에 프리플라이트를 실행해 행(hang)을 조기에 발견합니다. 긴 테스트를 트레이스백이 있는 실패로 전환합니다.

- 행 프리플라이트:
  - `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`
- 선택적 컬렉션 전용 점검:
  - `uv run -m pytest --collect-only -q`
- 전체 스위트(병렬):
  - `uv run -m pytest -W error -n auto`

작성자 노트:
- 60초를 초과할 것으로 예상되는 테스트에는 `@pytest.mark.timeout(180)` 등 개별 타임아웃을 설정하세요.
- 의도적으로 오래 걸리거나 외부 의존성을 가진 테스트는 `slow`로 표시하고 필요 시 프리플라이트에서 `-k 'not slow'`로 제외합니다.
- 결정적이며 의존성이 없는 테스트를 우선하고, 무제한 네트워크 대기는 피하세요.

## Pytest 플러그인은 최상위에만 선언

Pytest 8은 최상위 `conftest.py`가 아닌 곳에서 `pytest_plugins`를 정의하는 방식을 제거했습니다.

- `pytest_plugins = (...)`는 저장소 루트 `conftest.py`에서만 선언합니다.
- 하위 디렉터리의 `conftest.py`(예: `tests/` 하위)에는 지역 픽스처와 헬퍼만 두고 `pytest_plugins`를 선언하지 마세요.
- 서브트리 전역으로 픽스처를 공유하려면 일반 모듈(예: `tests/e2e/world_smoke/fixtures_inprocess.py`)에 정의하고 루트 `conftest.py`에서 등록하세요.

```python
# 저장소 루트의 conftest.py
pytest_plugins = (
    "tests.e2e.world_smoke.fixtures_inprocess",
    "tests.e2e.world_smoke.fixtures_docker",
)
```

Pytest는 실행 시 테스트 루트에 상대적인 최상위 `conftest.py`만 `pytest_plugins`를 읽습니다. 하위 선언은 무시되거나 이제는 오류를 발생시켜 컬렉션 시 픽스처 누락으로 이어질 수 있습니다.

팁:
- 항상 저장소 루트( `pytest.ini`가 있는 곳 )에서 pytest를 실행하세요. Pytest가 루트 디렉터리를 감지해 최상위 `conftest.py`를 불러옵니다.
- 하위 디렉터리에서 실행해도 `pytest.ini`를 통해 루트를 찾지만, 저장소 밖에서 실행할 경우 `-c path/to/pytest.ini`로 루트를 지정하세요.

## 마커와 병렬 실행

- 빠른 피드백을 위해 `pytest-xdist`의 `-n auto`로 병렬 실행하세요.
- 공유 리소스가 있는 스위트는 `--dist loadscope` 또는 `-n 2` 등으로 워커를 제한하고, 반드시 직렬이어야 하는 테스트는 분리 실행하세요.

## 공유 노드 팩토리

Gateway 및 SDK 테스트는 일관된 노드 해싱에 의존합니다. 직접 딕셔너리를 만들기보다 `tests/qmtl/runtime/sdk/factories/node.py`의 헬퍼를 재사용하세요. 팩토리는 파라미터를 정규화하고 의존성을 정렬하며 `node_id` 값을 계산해 해시 계약 변경이 한 곳에만 반영되도록 합니다.

```python
from tests.qmtl.runtime.sdk.factories import tag_query_node_payload, node_ids_crc32

node = tag_query_node_payload(tags=["t"], interval=60)
checksum = node_ids_crc32([node])
```

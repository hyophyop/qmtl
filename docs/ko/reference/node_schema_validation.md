---
title: "노드 DataFrame 스키마 검증"
tags: []
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# 노드 DataFrame 스키마 검증

노드는 `expected_schema` 를 선언해 입력되는 pandas `DataFrame` 페이로드를 검증할 수 있습니다. 스키마는 컬럼 이름을 dtype 문자열에 매핑하며, 데이터가 노드로 공급될 때 자동으로 확인됩니다.

## 스키마 선언

```python
from qmtl.runtime.sdk import SourceNode

price = SourceNode(
    interval="1s",
    period=1,
    expected_schema={"ts": "int64", "close": "float64"},
)
```

## 강제 모드

스키마 검사는 Runner의 `schema_enforcement` 플래그로 제어합니다.

- `fail` (기본): 불일치가 있으면 `NodeValidationError` 발생
- `warn`: 경고 로그를 남기고 계속 진행
- `off`: 검증을 건너뜀

```python
from qmtl.runtime.sdk import Runner

Runner.submit(MyStrategy, schema_enforcement="warn")
```

## 오류 메시지

`fail` 모드에서는 디버깅을 돕기 위해 노드 컨텍스트가 포함됩니다.

```
Node abc123: missing columns: ['close']
```

{{ nav_links() }}

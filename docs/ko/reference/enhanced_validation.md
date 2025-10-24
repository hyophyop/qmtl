---
title: "강화된 에러 처리 및 입력 검증"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 강화된 에러 처리 및 입력 검증

이 문서는 QMTL SDK의 에러 처리와 입력 검증 개선 사항을 설명합니다.

## Overview

QMTL SDK는 신뢰성을 높이고 개발자 경험을 개선하기 위해 포괄적인 입력 검증과 에러 처리를 포함합니다. 모든 검증은 정밀한 처리를 위해 커스텀 예외 타입을 사용합니다.

## 커스텀 예외 계층

```python
QMTLValidationError (base, inherits from ValueError)
├── NodeValidationError
    ├── InvalidParameterError
    ├── InvalidTagError
    ├── InvalidIntervalError
    ├── InvalidPeriodError
    └── InvalidNameError
```

## 검증 규칙

### 노드 파라미터

#### 이름(Name) 검증
- 문자열이거나 None이어야 함
- 비어있거나 공백만으로 구성될 수 없음
- 최대 길이: 200자
- 모든 노드 생성자에 적용

#### 태그(Tag) 검증
- 문자열이어야 함
- 비어있거나 공백만으로 구성될 수 없음
- 최대 길이: 100자
- 영숫자, 밑줄(`_`), 하이픈(`-`), 점(`.`)만 허용
- 단일 노드 내 중복 태그 금지
- `tags` 파라미터와 `add_tag()` 메서드에 적용

#### 인터벌(Interval) 검증
- 양의 정수 또는 유효한 시간 문자열("1s", "30m", "1h")이어야 함
- 최대값: 86400초(24시간)
- `interval` 파라미터에 적용

#### 기간(Period) 검증
- 양의 정수여야 함
- 최대값: 10000
- `period` 파라미터에 적용

#### 설정(Config) 및 스키마 검증
- 제공된 경우 딕셔너리여야 함
- `config`, `schema` 파라미터에 적용

### feed() 메서드 검증

`feed()` 메서드는 모든 파라미터를 검증합니다:

- `upstream_id`: 비어있지 않은 문자열이어야 함
- `interval`: 양의 정수
- `timestamp`: 음수가 아닌 정수
- `on_missing`: "skip" 또는 "fail"

### TagQueryNode 검증

- `query_tags`: 비어있지 않은 유효 태그 리스트여야 함
- 중복 태그 금지
- 각 태그는 위의 태그 검증을 통과해야 함

## 사용 예시

### 기본 사용
```python
from qmtl.runtime.sdk import SourceNode, InvalidTagError, InvalidParameterError

# Valid usage
node = SourceNode(
    name="my_node",
    tags=["tag1", "tag2"],
    interval="1h",
    period=100,
    config={"param": "value"}
)

# Error handling
try:
    invalid_node = SourceNode(
        tags=["valid", "invalid tag with spaces"],
        interval="1s",
        period=1
    )
except InvalidTagError as e:
    print(f"Tag validation failed: {e}")
```

### feed() 메서드 검증 예시
```python
node = SourceNode(interval="1s", period=10)

try:
    # This will raise InvalidParameterError
    node.feed(123, 60, 1234567890, {})  # upstream_id must be string
except InvalidParameterError as e:
    print(f"Feed validation failed: {e}")

# Valid usage
success = node.feed("upstream_1", 60, 1234567890, {"data": "value"})
```

### 예외 처리
```python
from qmtl.runtime.sdk import QMTLValidationError, NodeValidationError

try:
    node = SourceNode(interval="25h", period=1)  # Too large
except QMTLValidationError as e:  # Catches all validation errors
    print(f"Validation error: {e}")

try:
    node = SourceNode(tags=["invalid@tag"], interval="1s", period=1)
except NodeValidationError as e:  # Catches all node-related errors
    print(f"Node validation error: {e}")
```

## 마이그레이션 가이드

### 호환성 주의 사항(Breaking Changes)

1. **예외 타입 변경**: 일부 검증 에러는 다른 예외 타입을 발생시킵니다.
   - 인터벌 검증: `ValueError` → `InvalidIntervalError`
   - 기간 검증: `TypeError` → `InvalidPeriodError`
   - ProcessingNode 입력 검증: `ValueError` → `NodeValidationError`

2. **새 검증 규칙**: 기존에 허용되던 값 중 일부가 거부됩니다.
   - 24시간을 초과하는 인터벌
   - 10000을 초과하는 기간
   - 잘못된 태그 문자(공백, 특수 기호)
   - 중복 태그
   - 빈 이름/태그

### 테스트 업데이트

Update test exception expectations:
```python
# Old
with pytest.raises(ValueError):
    parse_period("invalid")

# New  
with pytest.raises(InvalidPeriodError):
    parse_period("invalid")
```

### 호환성

기존의 유효한 사용 패턴은 변경 없이 동작합니다. 과거에 허용되던 잘못된 입력만 이제 적절한 검증 예외를 발생시킵니다.

## 테스트

검증 로직은 50개 이상의 테스트 케이스로 다음을 포괄합니다:
- 모든 검증 규칙과 엣지 케이스
- 예외 계층 동작
- 기존 기능과의 통합
- 에러 메시지 명확성

테스트 실행:
```bash
pytest tests/qmtl/runtime/sdk/test_enhanced_validation.py -v
```

{{ nav_links() }}

# Enhanced Error Handling and Input Validation

This document describes the improvements made to error handling and input validation in the QMTL SDK.

## Overview

The QMTL SDK now includes comprehensive input validation and error handling to improve reliability and provide better developer experience. All validation uses custom exception types for precise error handling.

## Custom Exception Hierarchy

```python
QMTLValidationError (base, inherits from ValueError)
├── NodeValidationError
    ├── InvalidParameterError
    ├── InvalidTagError
    ├── InvalidIntervalError
    ├── InvalidPeriodError
    └── InvalidNameError
```

## Validation Rules

### Node Parameters

#### Name Validation
- Must be a string or None
- Cannot be empty or whitespace-only
- Maximum length: 200 characters
- Applied to all Node constructors

#### Tag Validation
- Must be strings
- Cannot be empty or whitespace-only
- Maximum length: 100 characters
- Must contain only alphanumeric characters, underscore (`_`), hyphen (`-`), or dot (`.`)
- No duplicate tags allowed in a single node
- Applied to `tags` parameter and `add_tag()` method

#### Interval Validation
- Must be positive integer or valid time string ("1s", "30m", "1h")
- Maximum value: 86400 seconds (24 hours)
- Applied to `interval` parameter

#### Period Validation
- Must be positive integer
- Maximum value: 10000
- Applied to `period` parameter

#### Config and Schema Validation
- Must be dictionaries if provided
- Applied to `config` and `schema` parameters

### Feed Method Validation

The `feed()` method now validates all parameters:

- `upstream_id`: Must be non-empty string
- `interval`: Must be positive integer
- `timestamp`: Must be non-negative integer
- `on_missing`: Must be "skip" or "fail"

### TagQueryNode Validation

- `query_tags`: Must be non-empty list of valid tags
- No duplicate tags allowed
- All individual tags must pass tag validation

## Usage Examples

### Basic Usage
```python
from qmtl.sdk import SourceNode, InvalidTagError, InvalidParameterError

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

### Feed Method Validation
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

### Exception Handling
```python
from qmtl.sdk import QMTLValidationError, NodeValidationError

try:
    node = SourceNode(interval="25h", period=1)  # Too large
except QMTLValidationError as e:  # Catches all validation errors
    print(f"Validation error: {e}")

try:
    node = SourceNode(tags=["invalid@tag"], interval="1s", period=1)
except NodeValidationError as e:  # Catches all node-related errors
    print(f"Node validation error: {e}")
```

## Migration Guide

### Breaking Changes

1. **Exception Types**: Some validation errors now raise different exception types:
   - `ValueError` → `InvalidIntervalError` for interval validation
   - `TypeError` → `InvalidPeriodError` for period validation
   - `ValueError` → `NodeValidationError` for ProcessingNode input validation

2. **New Validation Rules**: Some previously accepted values are now rejected:
   - Intervals > 24 hours
   - Periods > 10000
   - Invalid tag characters (spaces, special symbols)
   - Duplicate tags
   - Empty names/tags

### Updating Tests

Update test exception expectations:
```python
# Old
with pytest.raises(ValueError):
    parse_period("invalid")

# New  
with pytest.raises(InvalidPeriodError):
    parse_period("invalid")
```

### Compatibility

All existing valid usage patterns continue to work without changes. Only invalid inputs that were previously accepted will now raise appropriate validation errors.

## Testing

The validation is comprehensively tested with 50+ test cases covering:
- All validation rules and edge cases
- Exception hierarchy behavior
- Integration with existing functionality
- Error message clarity

Run validation tests:
```bash
pytest tests/test_enhanced_validation.py -v
```
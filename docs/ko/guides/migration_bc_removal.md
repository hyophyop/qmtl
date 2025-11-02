---
title: "마이그레이션: 레거시 모드 및 하위 호환성 제거"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-04
---

{{ nav_links() }}

# 마이그레이션: 레거시 모드 및 하위 호환성 제거

이 가이드는 레거시 호환 레이어 제거 내용을 요약하고, 코드 마이그레이션 방법을 제시합니다.

## Runner API

**변경 전**

```python
from qmtl import Runner

runner = Runner(...)
runner.backtest(strategy)
```

**변경 후**

```python
from qmtl.runtime.sdk import Runner

runner = Runner(...)
runner.run(strategy, world_id="demo", gateway_url="http://localhost:8000")
# or for local runs
runner.offline(strategy)
```

## CLI

**변경 전**

```bash
qmtl tools sdk --mode backtest --world-id demo --gateway-url http://localhost:8000
```

**변경 후**

```bash
qmtl tools sdk run --world-id demo --gateway-url http://localhost:8000
qmtl tools sdk offline  # local execution
```

## Gateway `/strategies`

**변경 전**

```json
{
  "run_type": "backtest",
  "strategy": {...}
}
```

**변경 후**

```json
{
  "world_id": "demo",
  "strategy": {...}
}
```

## Brokerage 임포트

**변경 전**

```python
from qmtl.runtime.brokerage.simple import PerShareFeeModel, VolumeShareSlippageModel
```

**변경 후**

```python
from qmtl.runtime.brokerage import PerShareFeeModel, VolumeShareSlippageModel
```

## 체크리스트

- [ ] `Runner.backtest`, `Runner.dryrun`, `Runner.live`를 `Runner.run` 또는 `Runner.offline`으로 교체
- [ ] CLI는 `--mode` 대신 `run`/`offline` 서브커맨드 사용
- [ ] Gateway `/strategies` 요청에서 `run_type` 제거, 필요 시 `world_id` 전달
- [ ] 브로커리지 헬퍼는 `qmtl.runtime.brokerage`에서 임포트(`.simple` 경로 사용 금지)

{{ nav_links() }}

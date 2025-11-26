---
title: "마이그레이션: 레거시 모드 및 하위 호환성 제거"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-04
---

{{ nav_links() }}

# 마이그레이션: 레거시 모드 및 하위 호환성 제거

이 가이드는 레거시 호환 레이어 제거 내용을 요약하고, 코드 마이그레이션 방법을 제시합니다.

## Runner API (v2 단일 엔트리포인트)

**변경 전 (레거시, 제거됨):** `backtest/dryrun/live/run/offline` 다중 엔트리포인트

**변경 후 (단일 API)**

```python
from qmtl.runtime.sdk import Runner, Mode

result = Runner.submit(MyStrategy, world="demo", mode=Mode.LIVE, preset="moderate")
print(result.status, result.world, result.mode)
```

## CLI

```bash
# 전략 제출 (프리셋 정책 포함)
qmtl submit my_strategy.py --world demo --mode live --preset aggressive

# 월드 생성/조회 (정책 프리셋 적용 및 설명)
qmtl world create demo --policy conservative
qmtl world info demo

# 운영자 커맨드가 필요하면 --admin 사용
qmtl --admin gw --config qmtl.yml
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

- [ ] 모든 `Runner.backtest` / `Runner.dryrun` / `Runner.live` / `Runner.run` / `Runner.offline` 호출을 `Runner.submit(..., mode=...)`로 교체
- [ ] CLI는 레거시 `service sdk run/offline` 대신 `qmtl submit --mode <backtest|paper|live> [--preset <name>]` 사용
- [ ] 월드 정책은 `qmtl world create --policy <preset>` 또는 `POST /worlds/{id}/policies`(preset/override 지원)로 설정
- [ ] `qmtl world info` 또는 `GET /worlds/{id}/describe`로 적용 정책 확인 (preset, version, human-readable 포함)
- [ ] Gateway `/strategies` 요청에서 `run_type` 제거 후 `mode`와 `world` 조합 사용
- [ ] 브로커리지 헬퍼는 `qmtl.runtime.brokerage`에서 임포트(`.simple` 경로 사용 금지)

{{ nav_links() }}

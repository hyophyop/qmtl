---
title: "정책 엔진"
tags: [world, policy]
author: "QMTL Team"
last_modified: 2025-08-21
---

# 정책 엔진

이 가이드는 월드 정책을 정의하고 적용하는 방법을 설명합니다.

## 샘플 정책

샘플 정책은 [`sample_policy.yml`](./sample_policy.yml)에 포함되어 있습니다:

```yaml
thresholds:
  sharpe:
    metric: sharpe
    min: 0.5
  drawdown:
    metric: drawdown
    max: 0.2
top_k:
  metric: sharpe
  k: 3
correlation:
  max: 0.8
hysteresis:
  metric: sharpe
  enter: 0.6
  exit: 0.4
```

## 정책 적용

WorldService API를 사용해 정책을 적용하고 전략을 평가합니다:

```bash
curl -X POST /worlds/alpha/apply \
  -H 'Content-Type: application/json' \
  -d '{"policy": { ... }, "metrics": { ... }}'
```

응답에는 평가 이후 활성화된 전략 목록이 포함됩니다.

```json
{
  "ok": true,
  "run_id": "...",
  "active": ["alpha-core", "alpha-hedge"],
  "phase": "completed"
}
```

`ok`는 기본적으로 `true`이며, `active`는 저장된 전략 목록을 반영합니다(활성 항목이 없으면 빈 배열). `phase`는 선택 항목으로, 성공 시 `completed`이며 2‑단계 Apply가 진행 중이면 해당 단계가 표시될 수 있습니다.

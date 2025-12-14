---
title: "Getting Started"
tags:
  - getting-started
  - onboarding
author: "QMTL Team"
last_modified: 2025-12-01
---

# Getting Started

!!! abstract "What is QMTL?"
    QMTL is a platform where you write and submit trading strategies, and the system is **designed to automate backtests, policy-based evaluation, and promotion/demotion decisions**.  
    Today it already automates backtesting and policy evaluation/demotion; **auto promotion, capital allocation, and real-time monitoring** are being rolled out incrementally.

## Core Value

> **"Focus only on strategy logic, and the system handles optimization and generates returns."**

```
┌─────────────────────────────────────────────────────────────┐
│                    What Users Do                            │
│                                                             │
│   1. Write Strategy  2. Submit (one line)  3. Check Results │
│   ┌─────────┐       ┌─────────┐          ┌─────────┐       │
│   │ class   │ ───▶  │ submit()│ ───▶     │ Metrics │       │
│   │ MyStrat │       └─────────┘          │ Rank    │       │
│   └─────────┘                            │ Alloc   │       │
│                                          └─────────┘       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                What the System Handles                      │
│   (Users don’t need internal details)                       │
│                                                             │
│   • Backtest execution and history replay (implemented)     │
│   • Performance evaluation (Sharpe, MDD, correlations, …)   │
│   • Validity checks and demotion handling (implemented)     │
│   • Auto promotion / capital allocation / live monitoring   │
│     (planned / rolling out over time)                       │
└─────────────────────────────────────────────────────────────┘
```

## Documentation Structure

| Document | Description | Time |
|----------|-------------|------|
| [Core Concepts](concepts.md) | Strategy, World, Stage — 3 things to know | 5 min |
| [Quickstart](quickstart.md) | From first strategy to submission | 10 min |
| [User Workflow](workflow.md) | Develop → Evaluate → Improve cycle | 15 min |

## Next Steps

- If you're new → Start with [Core Concepts](concepts.md)
- Want to dive in → Go to [Quickstart](quickstart.md)
- Curious about architecture → See [Architecture Overview](../architecture/README.md)

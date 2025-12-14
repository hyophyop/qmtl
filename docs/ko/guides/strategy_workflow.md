---
title: "전략 개발 및 테스트 워크플로"
tags: []
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# 전략 개발 및 테스트 워크플로

Core Loop 로드맵의 **Runner.submit + world/preset** 흐름을 그대로 따라 실행하는 것을 목표로 합니다. “월드 없이 단독 백테스트”는 부록으로 내려가며, 기본 경로는 WS 결정/활성(SSOT)과 일치하는 표면을 제공합니다.

## 0. 준비 — 설치와 프로젝트 생성

```bash
uv venv
uv pip install -e .[dev]
qmtl project init --path my_qmtl_project --preset minimal --with-sample-data
cd my_qmtl_project
```

- `strategy.py`는 Core Loop 예제 전략, `qmtl.yml`은 기본 월드/게이트웨이 설정을 포함합니다.
- 추가 노드를 만들려면 `generators/`, `indicators/`, `transforms/` 패키지를 사용하세요.

## 1. Core Loop 최소 전략 예제

`Runner.submit`만으로 실행되는 월드 기반 전략의 최소 형태입니다. world preset을 사용하면 `StreamInput`의 `history_provider`가 자동 주입됩니다.

```python
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput, ProcessingNode


class DemoStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["price"], interval=60, period=60)

        def compute(view):
            return {"alpha": float(view.last("price"))}

        alpha = ProcessingNode(input=price, compute_fn=compute, name="alpha")
        self.add_nodes([price, alpha])


if __name__ == "__main__":
    Runner.submit(DemoStrategy, world="demo_world", data_preset="ohlcv.binance.spot.1m")
```

## 2. 제출과 결과 읽기(WS SSOT)

```bash
uv run qmtl submit strategies.demo:DemoStrategy \
  --world demo_world \
  --data-preset ohlcv.binance.spot.1m \
  --output json
```

- **WS 봉투 = 단일 진실(SSOT)**: `ws.decision`/`ws.activation`은 WorldService 스키마 그대로 직렬화됩니다. CLI 텍스트의 `🌐 WorldService decision (SSOT)`와 동일합니다.
- **precheck 분리**: 로컬 ValidationPipeline 결과는 `precheck`에만 위치합니다.
- **default-safe**: `as_of`/dataset 메타가 누락되면 compute-only로 강등되고 `downgraded/safe_mode`가 최상단에 표시됩니다.
- 계약 스위트(`tests/e2e/core_loop`)가 위 스키마/강등 규칙을 고정합니다.

## 3. 데이터 preset 온램프

- `world.data.presets[]` 중 하나를 선택하면 Runner/CLI가 Seamless를 자동 구성해 `StreamInput.history_provider`에 주입합니다.
- 존재하지 않는 preset ID는 즉시 실패하며, 생략 시 첫 번째 preset을 사용합니다.
- 규약과 예시는 [world/world.md](../world/world.md)·[architecture/seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md)에 정리되어 있습니다.

## 4. Core Loop 흐름 점검 체크리스트

- 제출: `Runner.submit(..., world=..., data_preset=...)` 단일 표면만 사용합니다.
- 결과: `SubmitResult.ws.*`가 WS 봉투와 동일해야 하며 `precheck`는 참고용입니다.
- 활성화/배포: WS가 권한을 가집니다. 활성/가중치/TTL/etag는 WS 응답을 그대로 사용하고, 모호할 때는 compute-only로 강등합니다.
- 자본 배분: `qmtl world allocations|rebalance-*` 명령으로 월드 단위 비중을 확인·적용합니다.

## 5. 템플릿과 다음 단계

- Core Loop 정렬 템플릿: [sdk_tutorial.md](sdk_tutorial.md), [world/world.md](../world/world.md), [world/policy_engine.md](../world/policy_engine.md)
- Intent-first/리밸런싱 파이프라인: [reference/intent.md](../reference/intent.md), [operations/rebalancing_execution.md](../operations/rebalancing_execution.md)
- 운영/모니터링: [operations/monitoring.md](../operations/monitoring.md), [operations/activation.md](../operations/activation.md)

## 부록 — 레거시/백테스트 전용 경로

- 월드가 없는 로컬 실험은 `Runner.submit(...)`로 수행하세요. 이 경로는 Core Loop 계약에서 보조 흐름으로 취급되며, WS/활성/큐 결정 규칙을 우회하지 않습니다.
- TagQuery/WebSocket 세부 동작, 테스트 모드 시간 예산, backfill 팁 등은 [sdk_tutorial.md](sdk_tutorial.md)와 [operations/e2e_testing.md](../operations/e2e_testing.md)에서 확인할 수 있습니다.

{{ nav_links() }}

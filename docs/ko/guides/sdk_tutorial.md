---
title: "SDK 사용 가이드"
tags: []
author: "QMTL Team"
last_modified: 2025-12-05
---

{{ nav_links() }}

# SDK 사용 가이드

Core Loop 기반으로 전략을 작성하고 제출하는 최소 경로를 다룹니다. 월드 없이 돌아가는 백테스트는 보조 흐름이며, WS 결정/활성(SSOT)을 따르는 표면을 우선합니다.

## 0. 설치 및 프로젝트 시작

```bash
uv venv
uv pip install -e .[dev]
qmtl project init --path my_qmtl_project --preset minimal --with-sample-data
cd my_qmtl_project
```

## 1. Strategy 골격

`Strategy.setup()`에서 노드만 등록하면 됩니다. 가장 단순한 Core Loop 예제:

```python
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput, ProcessingNode


class MyStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["price"], interval=60, period=60)

        def compute(view):
            return {"alpha": float(view.last("price"))}

        self.add_nodes([price, ProcessingNode(input=price, compute_fn=compute, name="alpha")])


if __name__ == "__main__":
    Runner.submit(MyStrategy, world="demo_world", mode="backtest", data_preset="ohlcv.binance.spot.1m")
```

- `StreamInput`과 `ProcessingNode`는 가장 기본적인 소스/프로세싱 노드입니다.
- Tag 기반 멀티큐가 필요하면 `TagQueryNode`를 추가하고, WS 결정/큐 매핑은 Gateway/WS가 담당하도록 둡니다.

## 2. 제출 표면과 모드 규칙

- `Runner.submit(..., world=..., mode=backtest|paper|live, data_preset=...)`
- CLI는 동일하게 `qmtl submit strategies.my:MyStrategy --world ... --mode ... --data-preset ...`
- 노출 모드는 `backtest|paper|live`뿐이며 legacy 토큰(`offline`/`sandbox`)은 모두 `backtest`로 정규화합니다.
- WS `effective_mode`가 단일 권한이며 모호/누락/만료 시 compute-only(backtest)로 강등됩니다.
- `backtest/paper`에서 `as_of`나 `dataset_fingerprint`가 없으면 `downgraded/safe_mode`가 최상단에 표시됩니다.

| 입력/출력 | 규칙 |
| --- | --- |
| `--mode` | `backtest|paper|live`만 허용. 미지정 시 compute-only(backtest) 강등. |
| `execution_domain` 힌트 | 내부적으로 표준 모드로만 매핑되며 사용자 표면에서는 숨김. |
| WS 봉투 | `DecisionEnvelope`/`ActivationEnvelope` 스키마 그대로 직렬화. |
| `precheck` | 로컬 ValidationPipeline 전용, SSOT 아님. |

## 3. SubmitResult 읽기 (WS SSOT vs precheck)

`--output json` 예시(요약):

```json
{
  "strategy_id": "demo_strategy",
  "world": "demo_world",
  "mode": "backtest",
  "downgraded": true,
  "downgrade_reason": "missing_as_of",
  "ws": { "decision": { "...": "..." }, "activation": { "...": "..." } },
  "precheck": { "status": "validating", "violations": [] }
}
```

- `ws.*`만이 단일 진실(SSOT)입니다. CLI 텍스트의 `🌐 WorldService decision (SSOT)` 섹션과 동일합니다.
- `precheck`는 참고용이며 SSOT가 아닙니다. 계약 스위트(`tests/e2e/core_loop`)가 WS/Precheck 분리를 고정합니다.
- `downgraded/safe_mode`로 default-safe 강등 여부를 한눈에 확인합니다.

## 4. 데이터 preset 자동 연결

- `world.data.presets[]`에 선언된 preset을 선택하면 Seamless가 자동 구성되어 `StreamInput.history_provider`에 주입됩니다.
- 잘못된 preset ID는 즉시 실패하며, 생략 시 첫 번째 preset을 사용합니다.
- 규약과 예시는 [world/world.md](../world/world.md), [architecture/seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md)에 정리되어 있습니다.

```bash
uv run qmtl submit strategies.my:MyStrategy \
  --world demo_world \
  --data-preset ohlcv.binance.spot.1m \
  --mode backtest
```

## 5. 의도/주문 파이프라인(요약)

- Intent-first 레시피: `nodesets.recipes.make_intent_first_nodeset`, [reference/intent.md](../reference/intent.md)
- 주문 전달: `TradeOrderPublisherNode` + `Runner.set_trade_order_*` 훅(HTTP/Kafka/커스텀). 대상이 없으면 주문은 무시되어 전략 코드가 백엔드를 몰라도 됩니다.
- 리밸런싱 연결: [world/rebalancing.md](../world/rebalancing.md), [operations/rebalancing_execution.md](../operations/rebalancing_execution.md)

## 6. 캐시/테스트 팁

- `compute_fn`에는 읽기 전용 `CacheView`가 전달됩니다. `NodeCache.snapshot()`은 내부 구현으로 숨겨졌습니다.
- PyArrow 캐시/evict 간격, test_mode 시간 예산 등은 [operations/e2e_testing.md](../operations/e2e_testing.md)와 `cache.*` 설정을 참고하세요.
- 계약/단위 테스트는 `uv run -m pytest -W error -n auto`로 병렬 실행합니다.

## 부록 — TagQuery/웹소켓·타이밍·체결 모델 세부

- TagQueryManager/WebSocket 토큰 교환, 센티널 가중치 이벤트: [strategy_workflow.md](strategy_workflow.md) 부록 및 소스 코드 주석.
- `ExecutionModel`/`TimingController`를 활용한 실거래 비용·시장 시간 제약 시뮬레이션: [operations/timing_controls.md](../operations/timing_controls.md)와 예제(`qmtl/examples/strategies/order_pipeline_strategy.py`)를 참고하세요.
- 백필/데이터 준비: [operations/backfill.md](../operations/backfill.md)

{{ nav_links() }}

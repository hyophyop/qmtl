---
title: "QMTL 아키텍처 예시"
tags: [architecture, examples]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL 아키텍처 예시

본 문서는 [QMTL 규범 아키텍처](architecture.md)에서 분리한 비규범 예시 모음을 담습니다. 규범 경계와 SSOT 규칙은 아키텍처 본문을 따르고, 런타임 체크리스트와 운영 신뢰성 지침은 [아키텍처 런타임 신뢰성](../reference/architecture_runtime_reliability.md)을 참조합니다.

## 1. 일반 전략 예시 (Runner API 적용)

다음 예시는 사용자 정의 연산 함수, 노드 간 직접 참조, interval/period 기반 warmup 규칙을 함께 사용하는 가장 단순한 전략 패턴입니다.

```python
from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner
import polars as pl


class GeneralStrategy(Strategy):
    def setup(self):
        price_stream = StreamInput(
            interval="60s",
            period=30,
        )

        def generate_signal(view) -> pl.DataFrame:
            price = view.as_frame(price_stream, 60, columns=["close"]).validate_columns(["close"])
            momentum = price.frame.get_column("close").pct_change().rolling_mean(window_size=5)
            signal = (momentum > 0).cast(pl.Int64)
            return pl.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )

        self.add_nodes([price_stream, signal_node])


if __name__ == "__main__":
    Runner.submit(GeneralStrategy, world="general_demo")
```

## 2. Seamless Data Provider on-ramp

Seamless Data Provider는 히스토리/백필/라이브 소스의 단일 진입점입니다. 전략 코드는 `StreamInput`과 노드 로직만 선언하고, 데이터 경로 선택은 월드의 data preset과 Seamless preset 맵이 담당합니다.

- 구현 기준점: `qmtl/runtime/sdk/seamless_data_provider.py`
- 정합성/스키마 정규화: `qmtl/runtime/sdk/conformance.py`
- 단일 비행(backfill coordination): `qmtl/runtime/sdk/backfill_coordinator.py`
- SLA 레일: `qmtl/runtime/sdk/sla.py`

상세 계약은 [월드 데이터 preset 계약](../world/world_data_preset.md)과 [심리스 데이터 프로바이더 v2](seamless_data_provider_v2.md)에 정리합니다.

## 3. TagQuery 전략 예시

`TagQueryNode`는 큐 이름을 직접 고정하지 않고, 태그와 interval로 매칭되는 업스트림 큐 집합을 런타임에 해석합니다.

```python
from qmtl.runtime.sdk import Strategy, Node, Runner, TagQueryNode, MatchMode
import polars as pl


def calc_corr(view) -> pl.DataFrame:
    aligned = view.align_frames([(node_id, 3600) for node_id in view], window=24)
    frames = [frame.frame for frame in aligned if not frame.frame.is_empty()]
    if not frames:
        return pl.DataFrame()

    corr = pl.concat(frames, how="horizontal").corr()
    return corr


class CorrelationStrategy(Strategy):
    def setup(self):
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
            match_mode=MatchMode.ANY,
            compute_fn=calc_corr,
        )

        corr_node = Node(
            input=indicators,
            compute_fn=calc_corr,
            name="indicator_corr",
        )

        self.add_nodes([indicators, corr_node])


if __name__ == "__main__":
    Runner.submit(CorrelationStrategy, world="corr_demo")
```

동작 요약:

1. Runner가 `TagQueryManager`를 통해 Gateway `GET /queues/by_tag`를 호출합니다.
2. Gateway는 글로벌 DAG과 토픽 네임스페이스 정책을 바탕으로 매칭 큐를 반환합니다.
3. SDK는 매칭 큐의 데이터를 읽기 전용 `CacheView`로 합성해 `compute_fn`에 전달합니다.
4. 신규 큐가 발견되면 TagQueryManager가 런타임 중 업스트림 목록을 확장합니다.

큐 라우팅 규약은 [월드 데이터 preset 계약](../world/world_data_preset.md)과 [DAG Manager](dag-manager.md)에 위임합니다.

## 4. 교차 시장 전략 예시

다음 예시는 서로 다른 시장의 업스트림을 조합하되, 제출 표면은 동일하게 `Runner.submit(..., world=...)` 하나로 유지하는 패턴입니다.

```python
from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner
import polars as pl


def lagged_corr(view) -> pl.DataFrame:
    btc = pl.DataFrame([v for _, v in view[btc_price][60]])
    mstr = pl.DataFrame([v for _, v in view[mstr_price][60]])
    btc_shift = btc.get_column("close").shift(90)
    corr = btc_shift.pearson_corr(mstr.get_column("close"))
    return pl.DataFrame({"lag_corr": [corr]})


class CrossMarketLagStrategy(Strategy):
    def setup(self):
        btc_price = StreamInput(tags=["BTC", "price", "binance"], interval="60s", period=120)
        mstr_price = StreamInput(tags=["MSTR", "price", "nasdaq"], interval="60s", period=120)

        corr_node = Node(
            input=[btc_price, mstr_price],
            compute_fn=lagged_corr,
            name="btc_mstr_corr",
        )

        self.add_nodes([btc_price, mstr_price, corr_node])


Runner.submit(CrossMarketLagStrategy, world="cross_market_lag")
```

핵심 포인트:

- 입력 시장과 주문 대상 시장이 달라도 월드가 평가/활성/주문 게이트를 동일하게 제어합니다.
- 프로모션 전에는 `validate` 또는 `paper` 상태에서 동일 DAG를 관측하고, 승격 후에만 주문 경로를 엽니다.
- 전략 코드는 시장별 데이터 소스와 시차 계산만 신경 쓰고, 활성화/승격/안전 강등은 백엔드 계약에 위임합니다.

{{ nav_links() }}

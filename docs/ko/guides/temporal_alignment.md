# Temporal Alignment

Temporal alignment는 일봉, 시간봉, 호가처럼 시간 해상도와 도착 방식이 다른 입력을 하나의 aligned payload stream으로 만드는 SDK 기능입니다. 기존 `align_frames()`는 공통 timestamp 교집합을 유지하지만, temporal alignment는 trigger timestamp를 기준으로 exact/as-of/temporal lookup과 freshness 상태를 함께 반환합니다.

## 기본 패턴

```python
from qmtl.runtime.sdk import (
    AlignmentInputSpec,
    ProcessingNode,
    StreamInput,
    TemporalAlignedOutputSpec,
    TemporalSpec,
)

daily = StreamInput(
    tags=["krx", "daily"],
    interval="1d",
    period=1,
    temporal=TemporalSpec(kind="bar"),
    alignment=AlignmentInputSpec(alias="daily", partition_key="symbol"),
)
hourly = StreamInput(
    tags=["krx", "hourly"],
    interval="1h",
    period=1,
    temporal=TemporalSpec(kind="bar"),
    alignment=AlignmentInputSpec(alias="hourly", partition_key="symbol"),
)
book = StreamInput(
    tags=["krx", "book"],
    interval="1s",
    period=1,
    temporal=TemporalSpec(kind="event", idle_after="2s", sequence="seq"),
    alignment=AlignmentInputSpec(alias="book", partition_key="symbol"),
)

market_context = ProcessingNode(
    input=[daily, hourly, book],
    output=TemporalAlignedOutputSpec(trigger=book, partition_key="symbol"),
    interval="1s",
    period=1,
)

signal = ProcessingNode(
    input=market_context,
    compute_fn=lambda view: make_signal(
        view.window(market_context, market_context.interval, count=1).latest()
    ),
    interval="1s",
    period=1,
)
```

- `TemporalSpec(kind="bar")`는 일봉/시간봉처럼 완료 여부가 있는 바 입력에 사용합니다.
- `TemporalSpec(kind="event")`는 orderbook snapshot처럼 불규칙 이벤트로 도착하는 입력에 사용합니다.
- `AlignmentInputSpec(alias=...)`는 aligned payload 안에서 사용할 입력 이름을 지정합니다.
- `TemporalAlignedOutputSpec`를 가진 `ProcessingNode`는 사용자 `compute_fn` 없이 trigger 입력이 도착할 때 aligned payload를 output으로 방출합니다.
- `StreamInput`에 `temporal` metadata가 있으면 `JoinSpec`는 자동 추론됩니다. 추론할 수 없는 경우에는 예외가 발생하므로 필요한 정책을 빠뜨린 채 실행되지 않습니다.
- bar 입력은 기본적으로 `asof`와 `closed_only=True`로 추론되어 payload의 `is_final=False` 값을 제외합니다.
- trigger 입력은 기본적으로 `exact`로 추론됩니다.
- trigger가 아닌 event/state 입력은 `idle_after`, `max_age`, `tolerance` 중 하나가 필요합니다. 없으면 unbounded as-of가 위험하므로 예외가 발생합니다.
- `tolerance` 또는 `max_age`를 지정하면 선택된 입력이 오래되었을 때 `aligned.ready=False`와 `stale_inputs` 상태가 표시됩니다. 기본 `ready_only=True`에서는 not-ready payload가 downstream으로 방출되지 않습니다.
- `partition_key`와 `partition={"symbol": "005930"}`를 함께 사용하면 다종목 입력에서 심볼별 정렬을 수행합니다.
- 기본 추론이 맞지 않는 경우 `overrides={"book": {"max_age": "500ms"}}`처럼 필요한 입력만 덮어씁니다. 직접 `JoinSpec`를 넘기는 저수준 경로도 유지됩니다.

## 한국 주식 검증 시나리오

- 일봉 추세 + 시간봉 필터 + 현재 호가 진입: orderbook timestamp를 trigger로 두고 일봉/시간봉은 마지막 완료 바를 `asof`로 조회합니다.
- 시간봉 close 리밸런싱 + 최근 호가 실행가 판단: 시간봉 close timestamp를 trigger로 두고 orderbook은 bounded `asof`로 조회합니다.
- 장 시작 gap/시가 전략: session-open 또는 첫 quote를 trigger로 두고 전일 일봉은 temporal lookup으로 조회합니다.
- 호가 중심 market making + 일/시봉 regime filter: 빠른 orderbook trigger와 느린 bar context를 freshness 상태로 분리합니다.
- 휴장/거래정지/VI/orderbook idle 처리: market-status stream/table을 temporal reference로 조회합니다.
- 다종목 ranking + 심볼별 orderbook liquidity filter: `partition_key`와 optional input을 사용해 특정 종목 지연이 전체 유니버스를 막지 않게 합니다.
- corporate action 또는 revised daily bar: live/paper는 late data를 side output/drop으로 다루고, backtest/simulate는 recompute를 허용합니다.

## 범위

Temporal alignment는 `NodeCache` 저장 구조를 바꾸지 않습니다. KRX 휴장, 동시호가, 거래정지 같은 세부 규칙은 core에 넣지 않고 calendar/session adapter가 공급해야 합니다. Orderbook delta는 v1에서 직접 조인하지 않고 provider나 NodeSet이 검증한 snapshot/state stream으로 정규화한 뒤 사용합니다.

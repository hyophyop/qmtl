# CCXT 선물 레시피

이 가이드는 CCXT 선물 Node Set 레시피를 사용해 전략을 영구 선물 거래소(기본값: Binance USDT-M)에 연결하는 방법을 설명합니다. 레시피는 `NodeSetRecipe` 를 활용해 일관된 구성을 제공하며 레지스트리에 등록되어 어댑터와 테스트가 자동으로 정렬됩니다. 아키텍처 배경은 [거래소 Node Set](../architecture/exchange_node_sets.md) 문서를 참고하세요. `tests/qmtl/runtime/nodesets/test_recipe_contracts.py` 의 계약 테스트는 CCXT 스팟과 함께 이 레시피를 검증해 사이징/포트폴리오 주입과 노드 수 안정성을 보장합니다.

## 사용법

```python
import os

from qmtl.runtime.nodesets.registry import make

nodeset = make(
    "ccxt_futures",
    signal_node,
    "demo-world",
    exchange_id="binanceusdm",
    sandbox=True,
    apiKey=os.getenv("BINANCE_FUT_API_KEY"),
    secret=os.getenv("BINANCE_FUT_API_SECRET"),
    leverage=5,
    margin_mode="cross",
    hedge_mode=True,
)

strategy.add_nodes([price, alpha, history, signal_node, nodeset])
```

Node Set은 어댑터/도구 통합을 위한 메타데이터를 노출합니다.

```python
info = nodeset.describe()      # 노드 수 + 디스크립터
caps = nodeset.capabilities()  # ['simulate', 'paper', 'live'] 범위
```

레시피를 직접 임포트하는 것도 가능합니다.

```python
import os

from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset

nodeset = make_ccxt_futures_nodeset(
    signal_node,
    "demo-world",
    exchange_id="binanceusdm",
    leverage=10,
    reduce_only=True,
)
```

## 주문 파라미터 전달

선물 레시피는 스팟 체인(사전 검사 → 사이징 → 실행 → 주문 게시)과 유사하지만 선물 전용 기본값을 추가합니다.

- `time_in_force` 기본값은 `GTC` 입니다. 필요 시 레시피 인자로 재정의하세요.
- `reduce_only=True` 설정 시 게시되는 주문에 `reduce_only` 필드가 포함됩니다.
- `leverage` 는 주문 필드와 CCXT `set_leverage` API(지원 시)에 모두 적용됩니다.
- `margin_mode` (기본 `"cross"`)와 `hedge_mode` 는 클라이언트 초기화 과정에서 가능한 한 적용됩니다.

시그널 노드는 최소한 `action`, `size`, `symbol` 키를 포함하는 딕셔너리를 출력해야 하며 사이징 노드는 공유 포트폴리오 구성을 사용해 수량으로 변환합니다.

## 예시 전략

[`qmtl/examples/strategies/ccxt_futures_nodeset_strategy.py`]({{ code_url('qmtl/examples/strategies/ccxt_futures_nodeset_strategy.py') }}) 는 간단한 모멘텀 시그널을 선물 레시피에 연결하는 전체 흐름을 보여줍니다. Binance Futures 테스트넷 주문을 발행하는 명령형 데모는 [`qmtl/examples/brokerage_demo/ccxt_binance_futures_nodeset_demo.py`]({{ code_url('qmtl/examples/brokerage_demo/ccxt_binance_futures_nodeset_demo.py') }}) 를 참고하세요.

## 메모

- `apiKey`/`secret` 을 생략하면 `FakeBrokerageClient` 가 사용되어 시뮬레이션 모드로 실행됩니다.
- 샌드박스/테스트넷 모드에서는 자격 증명이 필수이며, 누락 시 `RuntimeError` 가 발생합니다.
- Binance USDT-M 심볼은 `BTC/USDT` 형태를 사용합니다. 접미사가 필요한 거래소(`BTC/USDT:USDT` 등)는 시그널/주문 페이로드에서 처리하고 전략별로 문서화하세요.
- 체결 수집은 기본적으로 스텁이며 필요하면 추후 웹훅이나 폴링을 통합하세요.
- 레시피를 확장할 계획이라면 `tests/qmtl/runtime/nodesets/test_recipe_contracts.py` 에 변형을 추가해 체인 길이, 지원 모드, 포트폴리오 주입이 계속 보장되도록 하세요.

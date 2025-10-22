---
title: "Lean Brokerage Model — Integration Guide"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Lean Brokerage Model — Integration Guide

## 관련 문서
- [Architecture Overview](README.md)
- [QMTL Architecture](architecture.md)
- [Gateway](gateway.md)
- [DAG Manager](dag-manager.md)
- [WorldService](worldservice.md)

아래는 \*\*Lean의 ‘브로커리지 모델(Brokerage Model)’\*\*을 구현할 때 필요한 핵심 기술과, 이를 **조합**해 “현실적인 체결·거래 제약”을 한 번에 모델링하는 설계 가이드입니다. 마지막에 **QMTL**로 옮겨 담는 방법(모듈 배치/파이프라인)도 제안합니다.

---

## 1) Lean의 브로커리지 모델이 하는 일(한눈 요약)

Lean에서 브로커리지 모델은 **브로커별 기본 규칙과 보조 모델들을 한 세트로 묶어** 보안종목(Security)에 적용합니다. 기본 초기화기는 이 세트를 각 종목에 내려서 **Fill / Slippage / Fee / BuyingPower / Settlement / Short Availability / Margin Interest** 등의 “현실 모델”을 자동 설정합니다. 또한 주문 제출 가능 여부(자금·규격·시장 시간·브로커 제한)를 사전에 검증하고, 계좌 유형(현금/마진), 유휴증거금 비율까지 함께 정의합니다. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings?utm_source=chatgpt.com)][1], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com)][2])

> 예) `InteractiveBrokersBrokerageModel`을 설정하면 IB 기본 수수료·레버리지·시장지원 범위·거래 시간 규칙 등과 함께, 해당 브로커 표준의 각종 하위 모델이 종목에 바인딩됩니다. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/interactive-brokers?utm_source=chatgpt.com)][3])

---

## 2) 구성 요소별로 필요한 기술

아래 기술 블록을 합치면 Lean이 하는 “브로커리지 현실화”를 구현할 수 있습니다.

### A. 주문 전 검증(Validation) & 기본 속성

* **IBrokerageModel 인터페이스**:

  * 계좌 유형, **RequiredFreeBuyingPowerPercent**(유휴 매수력 비율), 브로커별 **CanSubmit/CanExecuteOrder** 등 주문 가능 판정 API. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com)][2])
* **Order Properties / Time-in-Force**:

  * GTC/GTD/IOC/FOK 등의 만기 규칙, 브로커 기본 값 설정. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-properties?utm_source=chatgpt.com)][4], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Orders_1_1TimeInForce.html?utm_source=chatgpt.com)][5])
* **심볼 속성(SymbolProperties / DB)**:

  * **최소 호가단위(tick size)**, **로트/최소 주문수량**, **계약승수**, 종목 통화 등. 주문 호가/수량 검증·라운딩에 사용. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SymbolProperties.html?utm_source=chatgpt.com)][6])

### B. 시장 시간·캘린더

* **SecurityExchangeHours / MarketHoursDatabase**:

  * 정규·프리·애프터 마켓 시간, 조기폐장/휴장 포함. 오더 실행 가능 시간 판정에 사용. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SecurityExchangeHours.html?utm_source=chatgpt.com)][7])

### C. 매수력/레버리지(마진)

* **Buying Power Model (IBuyingPowerModel)**:

  * 주문 접수 전 **증거금/레버리지 가능 여부**와 최대 수량 판정. 브로커/시간대/상품에 따라 복잡한 규칙을 캡슐화. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source=chatgpt.com)][8], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IBuyingPowerModel.html?utm_source=chatgpt.com)][9])

### D. 체결 가격·수량

* **Fill Model**:

  * 주문타입별(시장가/지정가/스탑/개장·폐장가 등) **체결가·체결수량** 결정. **개장/폐장 옥션가격** 사용 가능. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com)][10])
* **Slippage Model**:

  * 스프레드·거래량 비중·시장충격 기반 슬리피지. 기본/사전구현 모델을 제공하고 커스터마이즈 가능. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts?utm_source=chatgpt.com)][11])

### E. 비용·현금흐름

* **Fee Model (IFeeModel)**:

  * 브로커·시장별 **거래 수수료** 구조(고정·퍼센트·브로커 특화). 체결 이벤트에 비용 반영. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts?utm_source=chatgpt.com)][12])
* **Settlement Model (ISettlementModel)**:

  * 현금 결제 주기/규칙, 시간 경과에 따른 자금 적용(Scan/ApplyFunds 호출). ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts?utm_source=chatgpt.com)][13])
* **Margin Interest Model**:

  * 차입금에 대한 일할 이자/월말 정산 등 마진 이자 모델. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/margin-interest-rate/key-concepts?utm_source=chatgpt.com)][14], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IMarginInterestRateModel.html?utm_source=chatgpt.com)][15])
* **CashBook/환전**:

  * 다통화 포트폴리오 현금 장부·환율변환·총자산 반영. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/cashbook?utm_source=chatgpt.com)][16], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1Cash.html?utm_source=chatgpt.com)][17])

### F. 공매도 가능수량(Short Availability)

* **IShortableProvider & 데이터셋**:

  * 대차 가능한 주식 수량·대차비용 모델링 → 없으면 공매도 주문 거부. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_source=chatgpt.com)][18], [[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/short-availability/key-concepts?utm_source=chatgpt.com)][19])

### G. 실거래/데이터 통합(브로커 연결 시)

* **IBrokerage / Factory / Data 핸들러**:

  * 실거래 연결은 `IBrokerage`(주문·계좌 API) + `IBrokerageFactory`로 구성, 실시간 데이터는 `IDataQueueHandler`, 실거래 중 히스토리는 `IHistoryProvider`, 데이터 다운로드는 `IDataDownloader`로 표준화. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IBrokerage.html?utm_source=chatgpt.com)][20], [[QuantConnect](https://www.quantconnect.com/docs/v2/lean-engine/contributions/brokerages/laying-the-foundation?utm_source=chatgpt.com)][21])

---

## 3) 어떻게 **조합**해서 쓸 것인가: “브로커리지 프로파일” 파이프라인

아래는 브로커리지를 하나의 **Profile**로 캡슐화해, 주문이 들어올 때 거치는 **전-중-후 파이프라인**입니다. (Lean의 기본 초기화기 방식과 동일한 철학)

### (0) 보안종목 초기화 시

* **SecurityInitializer ← BrokerageModel**

  * 해당 프로파일의 **Fill/Slippage/Fee/BuyingPower/Settlement/ShortAvailability/MarginInterest**를 종목에 세팅. 레버리지/시드/시드환전도 설정. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings?utm_source=chatgpt.com)][1])

### (1) Pre-Trade 검증

1. **시장 시간** 체크: `Security.Exchange.Hours`에서 현재 시각에 거래 가능한지, 연장장 제한 등 확인. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours?utm_source=chatgpt.com)][22])
2. **호가단위·로트·최소수량** 맞춤 라운딩/거부: `SymbolProperties` 참조. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SymbolProperties.html?utm_source=chatgpt.com)][6])
3. **Buying Power** 확인: 주문가치·증거금 사용량·유휴율(RequiredFreeBuyingPowerPercent) 판정. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source=chatgpt.com)][8], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com)][2])
4. **공매도 가능수량** 확인(숏이면): `IShortableProvider` 조회. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_source=chatgpt.com)][18])
5. **브로커 특화 제한**: IBKR 예) 연장장 특정 주문 비허용 등 `CanExecuteOrder`. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Brokerages_1_1InteractiveBrokersBrokerageModel.html?utm_source=chatgpt.com)][23])

### (2) Execution(체결 산출)

* **FillModel**로 주문타입별 체결가/수량 결정(호가/틱·바 활용, 옥션가격 가능). 이어서 **SlippageModel**로 슬리피지 가산. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com)][10])

### (3) Post-Trade 회계 처리

* **FeeModel**로 수수료 차감 → **SettlementModel**이 정해진 스케줄로 현금 반영 → **MarginInterest** 일할 적용 → **CashBook** 다통화 반영. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts?utm_source=chatgpt.com)][12])

> 이 전체를 브로커별 **Profile**(예: IBKR, Coinbase, Binance …)로 미리 묶어 두고, 전략에서 `SetBrokerageModel(BrokerageName.X, AccountType.Y)`처럼 선택만 하게 하는 것이 Lean의 사용성 포인트입니다. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/interactive-brokers?utm_source=chatgpt.com)][3])

---

## 4) 브로커리지 프로파일 설계 체크리스트(기술 포인트)

1. **SymbolProperties/DB 연동**

   * 틱사이즈·로트·최소주문·계약승수: 가격/수량 라운딩과 제한 체크의 기준값. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SymbolProperties.html?utm_source=chatgpt.com)][6])
2. **시장시간 캘린더**

   * `SecurityExchangeHours` + `MarketHoursDatabase`를 통한 정규/연장장·조기폐장·휴장. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SecurityExchangeHours.html?utm_source=chatgpt.com)][7])
3. **Buying Power/Margin**

   * 계좌 타입별(BuyingPowerModel) + 브로커 유휴율(IBrokerageModel) 조합. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source=chatgpt.com)][8], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com)][2])
4. **Fill/Slippage/Fee의 결합 순서**

   * Fill → Slippage(체결가 조정) → Fee(현금 차감). 모델은 종목 단위로 세팅(필요 시 커스텀). ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com)][10])
5. **Settlement & CashBook**

   * 시간 경과형 정산(Scan/ApplyFunds) + 다통화 잔고/환전 반영. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts?utm_source=chatgpt.com)][13])
6. **Short Availability**

   * 공매도 가능 수량/비용 미존재 시 주문 거부. 데이터셋 연동 옵션. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/short-availability/key-concepts?utm_source=chatgpt.com)][19])
7. **Order Properties/TIF**

   * IOC/FOK/GTD 등의 만기 규칙과 브로커 기본값 제공. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-properties?utm_source=chatgpt.com)][4], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Orders_1_1TimeInForce.html?utm_source=chatgpt.com)][5])
8. **브로커 고유 제한**

   * 예: 연장장 체결 불가, 특정 자산 미지원 → `CanExecuteOrder` 같은 훅에서 일괄 판정. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Brokerages_1_1InteractiveBrokersBrokerageModel.html?utm_source=chatgpt.com)][23])

---

## 5) QMTL에 이식할 때의 모듈 배치(권장 아키텍처)

> 목표: DAG 순수성 해치지 않으면서 **브로커리지 프로파일**을 한 번에 주입.

**① BrokerageProfile (전역 구성체)**

* 내부에 하위 모델들을 보유:
  `{ FillModel, SlippageModel, FeeModel, BuyingPowerModel, SettlementModel, ShortableProvider, MarginInterestModel, ExchangeHoursProvider, SymbolPropertiesProvider, OrderProperties }`
* 전략 시작 시 **SecurityInitializer** 역할로 각 종목에 주입. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings?utm_source=chatgpt.com)][1])

**② ExecutionNode (DAG 노드)**

* 입력: 주문, 시세(틱/바), 프로파일
* 단계: Pre-Trade 검증 → Fill → Slippage → Fee → 이벤트 출력
* 옵션: **IOC/FOK** 즉시 취소, **volume-limit**(부분체결) 등 현실화 규칙

**③ Portfolio/CashBook Service (러너 단계 또는 별도 노드)**

* Settlement 주기와 Margin Interest를 **시간 스케줄**에 따라 적용
* 다통화 **CashBook** 업데이트 및 환산 가치 계산 ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/cashbook?utm_source=chatgpt.com)][16])

**④ ShortableProvider (서비스/캐시)**

* 종목·날짜별 대차 가능 수량 제공(없으면 숏 주문 거부). ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_source=chatgpt.com)][18])

**⑤ ExchangeHours/Calendar Provider**

* 장 개폐/연장장/휴장 캘린더 조회로 주문 타임 윈도우 통제. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SecurityExchangeHours.html?utm_source=chatgpt.com)][7])

---

## 6) 예시: **IBKR 프로파일** 구성 레시피

* **BuyingPower**: 마진/현금 계좌별 모델 + 유휴율 세팅(브로커리지 모델). ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source=chatgpt.com)][8], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com)][2])
* **Fill**: Equity/Futures 기본 FillModel(개장·폐장 옥션 가격 지원) 사용. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com)][10])
* **Slippage**: 거래량 기반 또는 스프레드 기반 프리셋 중 선택. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts?utm_source=chatgpt.com)][11])
* **Fee**: IBKR 수수료 모델 사용(티어·최소수수료 등). ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts?utm_source=chatgpt.com)][12])
* **Settlement**: 주식 T+2/T+1 등 정산 규칙 모델. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/supported-models?utm_source=chatgpt.com)][24])
* **Short**: US Short Availability 데이터로 대차 가능 수량 적용. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equities-short-availability?utm_source=chatgpt.com)][25])
* **Hours**: 거래소 캘린더/연장장 제한(IBKR 모델의 `CanExecuteOrder`) 적용. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Brokerages_1_1InteractiveBrokersBrokerageModel.html?utm_source=chatgpt.com)][23])

---

## 7) 구현 순서(POC 체크리스트)

1. **Symbol/Hours Provider**(틱사이즈·로트·캘린더) → 주문 검증 통과율 테스트. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SymbolProperties.html?utm_source=chatgpt.com)][6])
2. **BuyingPowerModel** → 최대가능수량 API/유휴율 적용 단위테스트. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IBuyingPowerModel.html?utm_source=chatgpt.com)][9])
3. **Fill/Slippage/Fee** → 체결 이벤트에 슬리피지/수수료 반영 여부 검증. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com)][10])
4. **Settlement/Margin Interest** → 시간 경과형 현금흐름 시뮬레이션. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts?utm_source=chatgpt.com)][13])
5. **ShortableProvider** → 숏 거부/허용 케이스 회귀 테스트. ([[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_source=chatgpt.com)][18])
6. **통합 파이프라인 시나리오**(정규/연장장, IOC/FOK, 최소수량·틱사이즈 위반, 대규모 주문 등) 엔드투엔드 테스트.

---

### 마무리

Lean의 브로커리지 모델은 \*\*“브로커별 현실 모델 번들 + 사전 검증 훅”\*\*입니다. 위 블록(모델·프로바이더·캘린더·캐시북)을 **BrokerageProfile**로 묶고, **SecurityInitializer**를 통해 종목에 일괄 주입하면, QMTL에서도 **브로커 현황에 맞는 체결·비용·정산·제약**을 한 번에 재현할 수 있습니다. 실거래 연동까지 확장하려면 `IBrokerage`에 해당하는 \*\*거래/데이터 핸들러(브로커 커넥터)\*\*를 덧붙이면 됩니다. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings?utm_source=chatgpt.com)][1], [[QuantConnect](https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IBrokerage.html?utm_source=chatgpt.com)][20])

> 참고: 각 항목의 상세 동작·예제·사전구현 모델 목록은 Lean 공식 문서의 **Reality Modeling** 섹션(매수력/체결/슬리피지/수수료/정산/공매도)과 **Brokerages** 섹션(IBKR 등)을 보시면 신속히 구현 스펙을 확정할 수 있습니다. ([[QuantConnect](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts?utm_source=chatgpt.com)][26])

If you want, I can sketch a minimal **IBKR-like BrokerageProfile POC**(파이썬 의사코드)로 실행 순서(Pre→Fill→Slip→Fee→Settle)를 보여드릴게요.

---

## Integration Note: Worlds and Brokerage

- Activation vs. Execution: WorldService decides whether a strategy/side may trade (activation set). Brokerage models define how orders are validated and executed once allowed.
- Separation of concerns: Gateway/SDK enforce world activation via an order gate before invoking brokerage logic. Brokerage does not determine activation and remains broker‑specific.
- Safety: If activation is stale/unknown, orders are gated OFF regardless of brokerage model outcomes.

### QMTL Module Mapping (Implementation Pointers)

- Orders & TIF: `qmtl/runtime/brokerage/order.py` (`OrderType`, `TimeInForce`, extended `Order`)
- Fill: `qmtl/runtime/brokerage/fill_models.py` (market/limit/stop/stop-limit + IOC/FOK)
- Slippage: `qmtl/runtime/brokerage/slippage.py` (null/constant/spread/volume-share)
- Fees: `qmtl/runtime/brokerage/fees.py` (percent/per-share/composite)
- Symbol properties: `qmtl/runtime/brokerage/symbols.py` (tick/lot/min validation)
- Exchange hours: `qmtl/runtime/brokerage/exchange_hours.py` (regular/pre/post; holiday support is incremental)
- Shortable: `qmtl/runtime/brokerage/shortable.py` (default static provider)
- Profiles/Initializer: `qmtl/runtime/brokerage/profile.py` (`ibkr_equities_like_profile()`)
- Settlement & Interest: `qmtl/runtime/brokerage/settlement.py`, `qmtl/runtime/brokerage/interest.py` (skeletons)
- SDK Gate: `qmtl/runtime/sdk/order_gate.py` (activation gate helper)

See also: Reference API at `docs/reference/api/brokerage.md`.

[1]: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/settings?utm_source=chatgpt.com "Settings"
[2]: https://www.lean.io/docs/v2/lean-engine/class-reference/IBrokerageModel_8cs_source.html?utm_source=chatgpt.com "Common/Brokerages/IBrokerageModel.cs Source File"
[3]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/interactive-brokers?utm_source=chatgpt.com "Interactive Brokers"
[4]: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-properties?utm_source=chatgpt.com "Order Properties - QuantConnect.com"
[5]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Orders_1_1TimeInForce.html?utm_source=chatgpt.com "QuantConnect.Orders.TimeInForce Class Reference - LEAN"
[6]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SymbolProperties.html?utm_source=chatgpt.com "QuantConnect.Securities.SymbolProperties Class Reference"
[7]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1SecurityExchangeHours.html?utm_source=chatgpt.com "QuantConnect.Securities.SecurityExchangeHours Class ..."
[8]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/buying-power?utm_source=chatgpt.com "Buying Power"
[9]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IBuyingPowerModel.html?utm_source=chatgpt.com "QuantConnect.Securities.IBuyingPowerModel Interface ..."
[10]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts?utm_source=chatgpt.com "Trade Fills"
[11]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts?utm_source=chatgpt.com "Slippage"
[12]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/key-concepts?utm_source=chatgpt.com "Transaction Fees"
[13]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/key-concepts?utm_source=chatgpt.com "Settlement"
[14]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/margin-interest-rate/key-concepts?utm_source=chatgpt.com "Margin Interest Rate"
[15]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Securities_1_1IMarginInterestRateModel.html?utm_source=chatgpt.com "Lean: QuantConnect.Securities.IMarginInterestRateModel ..."
[16]: https://www.quantconnect.com/docs/v2/writing-algorithms/portfolio/cashbook?utm_source=chatgpt.com "Cashbook"
[17]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Securities_1_1Cash.html?utm_source=chatgpt.com "QuantConnect.Securities.Cash Class Reference"
[18]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IShortableProvider.html?utm_source=chatgpt.com "QuantConnect.Interfaces. IShortableProvider ..."
[19]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/short-availability/key-concepts?utm_source=chatgpt.com "Short Availability"
[20]: https://www.lean.io/docs/v2/lean-engine/class-reference/interfaceQuantConnect_1_1Interfaces_1_1IBrokerage.html?utm_source=chatgpt.com "QuantConnect.Interfaces.IBrokerage Interface Reference"
[21]: https://www.quantconnect.com/docs/v2/lean-engine/contributions/brokerages/laying-the-foundation?utm_source=chatgpt.com "Laying the Foundation"
[22]: https://www.quantconnect.com/docs/v2/writing-algorithms/securities/market-hours?utm_source=chatgpt.com "Market Hours"
[23]: https://www.lean.io/docs/v2/lean-engine/class-reference/classQuantConnect_1_1Brokerages_1_1InteractiveBrokersBrokerageModel.html?utm_source=chatgpt.com "Lean: QuantConnect.Brokerages. ..."
[24]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/settlement/supported-models?utm_source=chatgpt.com "Supported Models"
[25]: https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equities-short-availability?utm_source=chatgpt.com "US Equities Short Availability"
[26]: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts?utm_source=chatgpt.com "Reality Modeling"

{{ nav_links() }}

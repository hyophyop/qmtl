---
title: "백테스트 실행 정확도 향상: Lean 기능과 QMTL 통합"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

<!-- markdownlint-disable -->

# 백테스트 실행 정확도 향상: Lean 기능과 QMTL 통합

본 문서는 백테스트 체결의 현실성을 높이기 위해 Lean이 제공하는 “현실 모델링” 기능(주문 유형/정책, 슬리피지, 수수료, 유동성 제약, 체결 타이밍, 포지션 추적 등)을 요약하고, QMTL에 적용(통합)하는 설계를 제안합니다. 가능하면 순수 DAG 방식으로, 필요 시 외부 보조(브로커 에뮬레이터) 레이어를 결합하는 하이브리드 접근을 권장합니다.

- 주문 체결 정책 – 시장가·지정가·스톱·IOC·FOK 등 Time-in-Force 포함
- 슬리피지 모델 – 고정 비율, 거래량 비중, 마켓 임팩트, 스프레드 기반
- 수수료 모델 – 브로커/자산별 고정·퍼센트·티어 수수료
- 유동성 제약 – 바/틱 거래량 대비 체결 한도, 부분 체결 누적
- 체결 타이밍 – 동일 바/틱 vs 다음 바/틱, 세션 오픈/클로즈(MOO/MOC)
- 포지션 추적 – 보유 수량·평단가·평가액, 주문 상태(열림/부분/완료/취소)
- 데이터 해상도 – 틱/바 혼용, bid/ask vs last 가격 선택

---

## 1. 주문 체결 정책(시장가·지정가·IOC·FOK 등)

- IOC(즉시-또는-취소): 현재 시점 데이터로 부분 체결 가능분만 체결하고 즉시 잔량 취소
- FOK(전량-또는-취소): 단번에 100% 체결 불가 시 즉시 취소
- 지정가/스톱: 조건 충족 시까지 보류(여러 시점에 걸친 대기)

QMTL 통합
- 실행 노드에 상태를 두어(보류 주문 목록) 각 데이터 이벤트마다 체결 조건 평가, 부분 체결/취소/이월을 처리합니다.
- 같은 타임스탬프에서 체결 이벤트와 잔량 취소 이벤트를 함께 출력(IOC/FOK)하여 엄밀한 의미론을 유지합니다.

---

## 2. 슬리피지 모델링(스프레드·거래량·시간 기반)

- 기본(Null): 추가 비용 없이 시장가로 체결(기본 가정)
- 고정 비율(Constant): 체결가에 일정 비율 가감(예: 0.1%)
- 거래량 비중(Volume Share): `slippage_pct = k × (order_qty / bar_volume)^2`(상한 적용)
- 마켓 임팩트: 실행 시간, 변동성, 영구/일시 임팩트, 무작위성 포함한 정교 모델
- 스프레드 기반: 시장가 체결 시 bid/ask 측면 가격 사용(호가 데이터 보유 시)

QMTL 통합
- 실행 노드에서 이론 체결가 산출 후 슬리피지를 적용(매수 가산, 매도 감산). 모델은 파라미터/함수로 교체 가능.
- 거래량 데이터가 없으면 0 또는 스프레드 기반으로 대체(자산 특성 반영; FX/크립토 등).

---

## 3. 수수료(Commission) 모델

- 브로커/자산별 고정·퍼센트·티어 수수료를 지원하고, 체결 시점에 P&L에서 차감합니다.
- 간단한 함수(또는 테이블)로 구성 가능하며, 실행 노드에서 체결 이벤트와 함께 기록합니다.

---

## 4. 유동성 제약

- 한 바/틱의 거래량 대비 주문 한도(부분 체결 누적)와 호가 깊이 고려.
- 초과분은 미체결로 남기거나 다음 이벤트로 이월합니다.

---

## 5. 체결 타이밍

- 동일 바/틱 체결(Lean 기본) vs 다음 바/틱 체결(룩어헤드 방지): 옵션으로 제어(`delay_market_fill=True` 등)
- MarketOnOpen/Close(세션 오픈/클로즈 체결) 속성 지원

실용 가이드
- 고해상도 데이터(틱)가 있으면 항상 그것을 우선 사용해 인공 지연을 피합니다.
- 바만 있는 경우 옵션이 켜질 때만 다음 바 체결을 적용합니다.
- 다음 바가 존재하지 않는 말단 구간에서는 미체결로 남겨 무가 체결을 방지합니다.

---

## 6. 포지션 추적 & 주문 상태

- 보유 수량·평단가·평가액을 유지하고, 주문 상태(열림/부분/완료/취소)를 추적합니다.
- DAG 내부(상태형 노드) 또는 외부 모듈(브로커 에뮬레이터) 중 선택해 구현합니다.

---

## 7. 데이터 해상도 & 가격 소스

- 틱/바 혼용: 의사결정은 바, 실행은 틱으로 구동하는 하이브리드가 현실적입니다.
- 시장가 체결 시 bid/ask 사용(호가가 있을 때), 없으면 last+스프레드 추정.
- 다중 업스트림(신호+틱)에서 틱 이벤트가 실행 노드를 트리거하도록 스케줄링합니다.
- 성능: 틱‑단위 처리는 비용이 크므로 필요한 부분만 정교화하고, 나머지는 근사치로 대체합니다.

---

## 8. 구현 형태(상태형 DAG vs 외부 보조)

- 상태형 실행 노드(DAG 내부): 아키텍처 일관성·재사용성 우수, 순수 함수성 일부 희생.
- 외부 보조(브로커 에뮬레이터): 부분 체결·대기·회계를 단순하게 모델링, DAG 외부 루프와의 연계 필요.
- 권장: “가능한 많은 부분을 DAG 노드로, 본질적으로 순차가 필요한 회계/상태는 국소적 외부 헬퍼” 중도 해법.

Runner 통합
- 그래프에서 신호를 생성한 뒤 실행 단계에서 슬리피지/수수료/유동성을 적용해 체결 이벤트를 만들고, 필요 시 포트폴리오 업데이트 노드/서비스로 연결합니다.

---

## 9. 결론

QMTL는 Lean의 현실 모델링 개념을 받아들여, 실행 현실성을 좌우하는 핵심 기능(주문 정책, 슬리피지, 수수료, 유동성, 타이밍, 포지션 추적, 데이터 해상도)을 단계적으로 통합할 수 있습니다. 구현은 상태형 실행 노드(순수 DAG 내부)와 외부 보조 레이어(브로커 에뮬레이터) 중 환경/요구에 맞게 선택하고, 인터페이스를 명확히 해 재사용성과 테스트 용이성을 확보합니다.

---

## 참고 자료

[1] [13] [14] [15] [18] [25] [26] [27] [28] [29] [30] FillModel.cs  
https://github.com/QuantConnect/Lean/blob/93d58d5cdfac666f2d5207ba1901b2c221729249/Common/Orders/Fills/FillModel.cs

[2] TimeInForce.cs  
https://github.com/QuantConnect/Lean/blob/93d58d5cdfac666f2d5207ba1901b2c221729249/Common/Orders/TimeInForce.cs

[3] [4] [5] [6] [7] [8] [9] [10] [11] [12] [16] [17] [22] [34] Supported Models - QuantConnect.com  
https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models

[19] FeeModel.cs  
https://github.com/QuantConnect/Lean/blob/93d58d5cdfac666f2d5207ba1901b2c221729249/Common/Orders/Fees/FeeModel.cs

[20] [21] [33] How to make Set SlippageModel and FeeModel work? - QuantConnect.com  
https://www.quantconnect.com/forum/discussion/17157/how-to-make-set-slippagemodel-and-feemodel-work/

[23] [24] [31] Market Order Backtesting Behavior - QuantConnect.com  
https://www.quantconnect.com/forum/discussion/10369/market-order-backtesting-behavior/

[32] [35] [architecture.md](../architecture/architecture.md)

{{ nav_links() }}


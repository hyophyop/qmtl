# 브로커리지 모델 기본 가정

QMTL 브로커리지 레이어는 초기 구현을 의도적으로 단순하게 유지합니다. 예제는 대규모 데이터 없이도 실행 가능하도록 하면서 확장 지점을 명확히 남겨둡니다.

- **틱/호가 단위:** `SymbolPropertiesProvider` 는 자산군 기본값(예: 주식은 틱 `0.01`, 호가 `1`)을 적용합니다. 주문은 해당 값으로 검증되며, 커스텀 테이블이나 파일을 제공해 덮어쓸 수 있습니다.
- **거래 시간 & 캘린더:** `ExchangeHoursProvider.with_us_sample_holidays` 는 일부 공휴일과 조기 마감이 포함된 간단한 미국 주식 일정을 제공합니다. 완전하지 않으므로 프로덕션에서는 전체 캘린더를 제공하세요.
- **공매도:** `ShortableProvider` 를 지정하지 않으면 매도 주문은 무제한 공매도가 가능하다고 가정합니다. `StaticShortableProvider` 또는 커스텀 프로바이더를 연결해 대여 한도와 수수료를 강제하세요.
- **슬리피지 & 수수료:** 예제는 단순함을 위해 `ConstantSlippageModel` 과 `PercentFeeModel` 을 사용합니다. 보다 현실적인 모델이 필요하면 `SpreadBasedSlippageModel`, `IBKRFeeModel`, `CompositeFeeModel` 등을 사용하세요.
- **결제:** `SettlementModel` 은 기본적으로 즉시 현금 이동을 가정합니다. T+N을 시뮬레이션하려면 `defer_cash=True` 를 활성화하고 `CashWithSettlementBuyingPowerModel` 과 함께 사용하세요.

이 가정은 [브로커리지 API](api/brokerage.md) 의 세부 사항과 [린 브로커리지 모델](../architecture/lean_brokerage_model.md) 설계 노트를 보완합니다.

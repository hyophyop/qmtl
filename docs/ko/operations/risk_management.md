---
title: "리스크 관리 가이드"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 리스크 관리 가이드

이 가이드는 백테스트와 시뮬레이션 중 포트폴리오 한도를 강제하기 위해 `RiskManager`를 구성하고 사용하는 방법을 설명합니다.

## 구성(Configuration)

`RiskManager`는 포트폴리오 제약을 정의하는 :class:`RiskConfig` 데이터클래스를 받습니다.
구성에는 다음과 같은 일반 임계값이 포함됩니다:

- `max_position_size`: 절대 포지션 최대값
- `max_leverage`: 허용 레버리지 최대치
- `max_drawdown_pct`: 허용 최대 손실률
- `max_concentration_pct`: 단일 종목 집중도 상한
- `max_portfolio_volatility`: 연율화 변동성 임계값
- `position_size_limit_pct`: 종목당 포트폴리오 비중 최대치
- `enable_dynamic_sizing`: 한도 충족을 위한 자동 사이징 여부

`:class:`RiskConfig`` 인스턴스를 바로 전달하거나, 필요한 필드만 인라인으로 덮어쓸 수 있습니다:

```python
from qmtl.runtime.sdk.risk_management import RiskConfig, RiskManager

config = RiskConfig(position_size_limit_pct=0.10)
risk_mgr = RiskManager(config=config, max_leverage=2.0)
```

## 포지션 한도 강제

`validate_position_size`로 제안된 트레이드를 검사할 수 있습니다. 반환값에는 거래 유효성, 위반 상세, 한도 충족을 위한 조정 수량이 포함됩니다.

```python
from qmtl.examples.strategies.risk_managed_strategy import enforce_position_limit

is_valid, violation, adjusted_qty = enforce_position_limit(
    symbol="AAPL", proposed_quantity=20, price=10.0, portfolio_value=1_000.0
)
```

설정된 한도를 초과하면 `is_valid`는 `False`이며, `adjusted_qty`에는 안전한 최대 수량이 반환됩니다.

{{ nav_links() }}

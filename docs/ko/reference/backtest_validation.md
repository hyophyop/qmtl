---
title: "백테스트 데이터 검증"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 백테스트 데이터 검증

`validate_backtest_data`는 리플레이 전에 캐시된 히스토리를 검사하여 흔한 품질 문제를 잡아냅니다. 각 `StreamInput`에 대해 `DataQualityReport`를 생성하며, 품질 점수가 임계값 아래로 떨어지면 실행을 중단할 수 있습니다.

## 수행되는 검사 항목

- **타임스탬프 갭** – 허용 오차를 초과하는 누락 구간
- **잘못된 가격** – 비수치 값 또는 허용 범위를 벗어난 값
- **의심스러운 변동** – `max_price_change_pct`를 초과하는 단일 구간 가격 변화
- **누락된 필드** – 필수 OHLC 필드가 없거나 null

## 구성 옵션

`BacktestDataValidator`는 다음 옵션을 받습니다:

| 옵션 | 설명 |
| --- | --- |
| `max_price_change_pct` | 단일 구간에서 허용되는 최대 변화율 (기본값 `0.1` = 10%) |
| `min_price` | 허용되는 최소 가격 값 |
| `max_gap_tolerance_sec` | 허용되는 최대 타임스탬프 간격(초) |
| `required_fields` | 각 레코드에 반드시 존재해야 하는 필드 목록 |

최소 품질 점수를 강제하려면 `validate_backtest_data(strategy, fail_on_quality_threshold=0.8)`를 사용하세요.

러너 통합:
- 로컬 백테스트의 경우 `Runner.submit(MyStrategy, mode=Mode.BACKTEST)`를 사용하고, 설정 또는 사전 점검 단계에서 검증을 호출합니다.
- WS 우선 실행의 경우 `Runner.submit(MyStrategy, world="name", mode=Mode.PAPER)`를 사용하고, 필요하면 검증을 별도의 프리플라이트 단계로 유지합니다.

## 예시

`qmtl/examples/backtest_validation_example.py` 스크립트는 오프라인 또는 WS 환경에서 실행하기 전에 검증을 활성화하는 방법을 보여줍니다. 실험을 위해 의도적으로 갭이 포함된 샘플 CSV는 `qmtl/examples/data/backtest_validation_sample.csv`에 제공됩니다.

{{ nav_links() }}

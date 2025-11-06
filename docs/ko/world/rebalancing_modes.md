---
title: "리밸런싱 모드: 스케일링 vs 오버레이"
tags: [world, rebalancing]
last_modified: 2025-11-04
---

# 리밸런싱 모드: 스케일링 vs 오버레이

정의
- 스케일링(Scaling): 각 전략 슬리브의 종목별 타깃 벡터에 스칼라 계수만 곱해 규모를 조절합니다. 상대 구조는 보존됩니다.
- 오버레이(Overlay): 하위 포지션을 건드리지 않고, 월드 상단에서 지수선물/ETF/퍼프(Perp) 등 대리 종목으로 목표 노출 차이를 메웁니다.

차이(핵심)
- 스케일링: 종목 레벨 정합(TE↓), 거래빈도↑(수수료/슬리피지), 유동성/틱 제약 영향
- 오버레이: 알파 간섭↓, 비용↓, 베이시스/펀딩/증거금 리스크↑

QMTL에서의 선택
- `POST /rebalancing/plan|apply` 요청에 `mode`를 지정합니다.
  - `mode: scaling` (기본): 스케일링 플래너 사용
  - `mode: overlay`: (현재 미구현 — 호출 시 NotImplementedError)
  - `mode: hybrid`: (현재 미구현 — 호출 시 NotImplementedError)

요청 확장(오버레이)
```json
{
  "mode": "overlay",
  "overlay": {
    "instrument_by_world": {"a": "ES_PERP", "c": "BTCUSDT_PERP"},
    "price_by_symbol": {"ES_PERP": 5000.0, "BTCUSDT_PERP": 60000.0},
    "min_order_notional": 50.0
  }
}
```

상태
- 오버레이/하이브리드는 현재 설계 논의가 필요한 단계이며, 호출 시 NotImplementedError가 발생합니다. 스케일링만 지원합니다.

게이트웨이 실행
- `POST /rebalancing/execute`는 `mode`와 `shared_account` 플래그에 따라 동작하지만, `overlay`/`hybrid`는 현재 미구현(NotImplementedError)입니다.

모듈 교체(플러그형)
- 스케일링 엔진은 활성화되어 있습니다(`MultiWorldProportionalRebalancer`).
- 오버레이/하이브리드는 인터페이스만 정의되었고 비활성(호출 시 NotImplementedError)입니다. 후속 설계 논의 후 활성화됩니다.

{{ nav_links() }}

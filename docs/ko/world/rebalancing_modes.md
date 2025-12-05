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
  - `mode: overlay`: 오버레이 대리종목을 사용해 월드 총 노출을 스케일링합니다.
  - `mode: hybrid`: (현재 미구현 — 호출 시 HTTP 501)

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
- 오버레이는 `overlay.instrument_by_world`, `overlay.price_by_symbol`이 함께 전달될 때 동작합니다. 구성값이 없으면 HTTP 422를 반환합니다. 하이브리드는 여전히 미구현이며 HTTP 501을 반환합니다.

게이트웨이 실행
- `POST /rebalancing/execute`는 `mode`와 `shared_account` 플래그에 따라 동작합니다. 오버레이 플랜에는 월드별 오버레이 주문(`overlay_deltas`)이 포함됩니다. 하이브리드는 미구현이며 HTTP 501을 반환합니다.

모듈 교체(플러그형)
- 스케일링 엔진은 활성화되어 있습니다(`MultiWorldProportionalRebalancer`).
- 오버레이 플래너는 구성값이 있을 때 활성화되며, 하이브리드는 설계가 완료될 때까지 비활성 상태입니다.

!!! note "Core Loop 범위"
    Core Loop P0/P1 관점에서는 **스케일링 모드가 기본 경로**이며, 오버레이/하이브리드 모드는 월드 리밸런싱의 고급 옵션으로 남겨져 있습니다.  
    오버레이는 구성과 리스크 모델이 갖춰진 환경에서만 사용해야 하며, 하이브리드는 HTTP 501로 명시적으로 막혀 있어 현재 로드맵 작업 범위 밖입니다.

{{ nav_links() }}

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
  - `mode: overlay`: 오버레이 플래너 사용(하위 포지션 무개입)
  - `mode: hybrid`: 두 결과를 함께 반환(overlay_deltas + per_world)

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

응답 확장
- `overlay_deltas`: 오버레이 방식으로 산출된 대리 종목 델타(수량)
- 스케일링 결과는 기존 필드(`per_world`, `global_deltas`)에 제공

게이트웨이 실행
- `POST /rebalancing/execute`는 `mode`와 `shared_account` 플래그에 따라
  - 스케일링(기본): `orders_per_world` 생성
  - 공유계정 전역 넷팅: `orders_global`(global_deltas)
  - 오버레이/하이브리드: `orders_global`(overlay_deltas)

모듈 교체(플러그형)
- WorldService는 모드에 따라 엔진을 선택해 호출합니다.
  - Scaling: `MultiWorldProportionalRebalancer`
  - Overlay: `OverlayPlanner`
  - Hybrid: 둘 다 실행하여 결합 응답 구성
- 동일 인터페이스(`MultiWorldRebalanceRequest/Response`)로 교체 가능하므로 API/클라이언트는 그대로 재사용됩니다.

{{ nav_links() }}


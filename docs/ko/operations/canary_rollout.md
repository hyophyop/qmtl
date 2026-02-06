---
title: "카나리아 롤아웃 가이드"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 카나리아 롤아웃 가이드

전략 버전 간 트래픽 분할은 내부 **ControlBus**에 `sentinel_weight` 이벤트를 게시하여 조정합니다.
운영 도구는 목표 `sentinel_id`와 원하는 `weight`(0–1)를 포함해 이벤트를 발행해야 합니다. Gateway는 ControlBus를
구독하고 이 변경 사항을 WebSocket으로 SDK 클라이언트에 중계합니다.

## 가중치 조정

1. 운영 도구로 ControlBus에 `sentinel_weight` 이벤트를 게시합니다.
2. `sentinel_id` 식별자와 `0`부터 `1` 사이의 `weight`를 포함합니다.
3. Gateway가 새 비율을 적용하고 연결된 클라이언트에 브로드캐스트합니다.

## 모니터링 지표

* **Gateway 지표:** Prometheus에서 `gateway_sentinel_traffic_ratio{sentinel_id="v1.2.1"}`를 확인해 라이브 트래픽 분할을 검증합니다. 이 지표는 Gateway의 `/metrics` 엔드포인트에서 노출되며 `sentinel_weight` 이벤트가 처리될 때 즉시 갱신됩니다.
* **Skew 가드레일:** `sentinel_skew_seconds{sentinel_id="v1.2.1"}`를 모니터링하여 발행자 대비 Gateway가 ControlBus 업데이트를 신속히 수신하는지 확인합니다.
* **DAG Manager 지표:** 각 버전에 대해 `dagmanager_active_version_weight`를 모니터링하여 가중치 적용을 확인합니다. DAG Manager의 `/metrics`에서 확인할 수 있습니다.
* **알림:** `alert_rules.yml`의 규칙은 5분 이상 구성 값에서 트래픽 가중치가 벗어나면 경고를 트리거합니다.

Grafana 대시보드로 카나리아 성공률과 에러 버짓을 시각화하면서 트래픽 가중치를 점진적으로 올리세요.

{{ nav_links() }}

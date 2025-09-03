---
title: "FAQ"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# FAQ

## 태그 기반 노드는 월드 주도 실행에서 어떻게 동작하나요?

`TagQueryNode`는 Runner가 생성하는 `TagQueryManager`가 Gateway와 통신하여 큐 목록을 갱신합니다. 월드 주도 실행에서 전략은 `Runner.run(world_id=..., gateway_url=...)`로 시작하며, 이때 TagQueryManager가 초기 큐 조회와 WebSocket 구독을 설정합니다. Gateway/WorldService가 연결되지 않으면 전략은 안전기본(compute‑only, 주문 게이트 OFF)으로 유지됩니다. `Runner.offline()` 은 Gateway 없이 로컬 실행으로, 태그 기반 노드는 빈 큐 목록으로 초기화됩니다.

{{ nav_links() }}

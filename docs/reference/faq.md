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

## 테스트가 가끔 hang 되거나 자원이 해제되지 않는 것 같습니다. 어떻게 방지하나요?

- 테스트 종료 시 백그라운드 서비스 정리:
  - `Runner.shutdown(strategy)` 또는 `await Runner.shutdown_async(strategy)`를 호출하여 `TagQueryManager`/`ActivationManager`를 정리하세요.
- 보수적인 타임아웃 적용:
  - 테스트 실행 전에 `QMTL_TEST_MODE=1`을 설정하면 SDK의 기본 HTTP/WS 타임아웃이 짧게 설정되어 hang 가능성이 줄어듭니다.
- ASGI/Transport 자원 정리:
  - FastAPI 수명 주기를 적용하려면 `httpx.ASGITransport(app, lifespan='on')` 를 사용하고 테스트 마지막에 `await transport.aclose()`로 명시적으로 자원을 해제하세요.
  - Gateway 앱은 백그라운드 태스크를 시작하지 않도록 `create_app(enable_background=False)` 옵션을 제공합니다. 단위 테스트에서는 이 플래그를 끄면 리소스 경합과 경고를 줄일 수 있습니다.

{{ nav_links() }}

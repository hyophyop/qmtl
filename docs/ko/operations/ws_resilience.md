---
title: "WS 전용 복원력 및 복구"
tags: []
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# WS 전용 복원력 및 복구

이 가이드는 QMTL이 큐 업데이트와 제어 이벤트의 WebSocket 전용 경로를 어떻게 처리하는지, 그리고 재연결 이후 중복 처리를 어떻게 방지하는지 설명한다.

## 동작 개요

- 중앙 관리자: SDK의 `TagQueryManager`가 초기 tag → queue 해상도를 HTTP로 수행하고, Gateway WebSocket 업데이트를 구독해 동적 변화를 추적한다.
- 재연결: SDK WebSocket 클라이언트는 heartbeat ping과 bounded backoff를 사용해 끊어진 연결을 감지하고 자동 복구한다.
- 백프레셔: Gateway WS 허브는 버퍼가 가득 차면 최신 메시지를 드롭하는 단순 정책을 적용하고, 상위 idempotency에 의존한다.

## 중복 방지

QMTL은 계층화된 idempotency로 중복 처리를 방지한다.

- SDK `NodeCache`는 replay 중복 제거에 쓰이는 `input_window_hash`를 생성한다.
- Gateway commit-log consumer는 sliding window 안에서 메시지 키 기준 중복 레코드를 버린다.
- WS 허브는 재시도 중 발생한 CloudEvent ID 중복을 차단한다.

그 결과, 연결이 끊겼다가 복구된 뒤에도 노드는 동일 `(node_id, bucket_ts, input_window_hash)`에 대해 중복 compute 실행 없이 재개된다.

## 운영 가이드

- 테스트와 staging에서는 짧은 timeout(`test.test_mode: true`)을 선호해 재연결 경로를 빨리 드러내라.
- 장시간 soak 동안에는 다음을 모니터링한다.
  - `gateway_ws_duplicate_drop_total`(활성화된 경우)과 commit-log duplicate 카운터
  - circuit 상태를 나타내는 `dagclient_breaker_*` / `kafka_breaker_*` gauge
- 테스트에서는 `Runner.session(...)`을 사용해 `TagQueryManager`와 background task가 종료 시 정리되도록 한다.

{{ nav_links() }}

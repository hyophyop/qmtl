---
title: "TagQuery 레퍼런스"
tags: []
author: "QMTL Team"
last_modified: 2025-09-23
---

{{ nav_links() }}

# TagQuery 레퍼런스

- 개요: `TagQueryNode`는 태그 집합과 인터벌을 기준으로 상위 큐를 선택합니다. Runner는 전략별 `TagQueryManager`를 연결해 최초 큐 목록을 해석하고 WebSocket을 통해 라이브 업데이트를 적용합니다.
- 엔드포인트: Gateway는 `GET /queues/by_tag` 를 제공하며, 파라미터는 `tags`(콤마 구분), `interval`(초), `match_mode` (`any`|`all`), `world_id`(선택)입니다.
- 매칭: `match_mode=any` 는 하나라도 포함된 큐를, `all` 은 모든 태그가 있는 큐만 선택합니다. 태그는 공백을 제거하고 정규화된 뒤 정렬되어 안정적인 키를 제공합니다.
- 정규화: Gateway는 다음과 같은 디스크립터 객체 배열을 반환합니다.
  - `{"queue": "<id>", "global": <bool>}`. `global=true` 인 항목은 실행 노드에서 무시됩니다.

## Runner 통합

- 부팅 시퀀스: `Runner.submit(..., world="name", mode=Mode.PAPER)` 은 `TagQueryManager`를 부착하고 Gateway의 `queue_map`을 노드에 적용한 뒤, 라이브 구독을 시작하기 전에 `resolve_tags()` 를 한 번 호출합니다.
- 라이브 업데이트: 부팅 이후 `TagQueryManager.start()` 는 `/events/subscribe` 에 구독하고, `/queues/by_tag` 를 주기적으로 호출해 편차를 복구합니다.
- 오프라인 모드: `Runner.submit(..., mode=Mode.BACKTEST)` 을 사용하거나 Gateway/Kafka를 이용할 수 없을 때 `resolve_tags(offline=True)` 는 로컬 캐시 파일(`.qmtl_tagmap.json` 기본값)에서 큐 매핑을 복원합니다. 스냅샷이 없으면 노드는 초기에는 데이터 없이 실행 전용으로 유지됩니다.

## 캐싱과 결정성

- 각 resolve 호출은 태그→큐 매핑 스냅샷을 `.qmtl_tagmap.json` 에 기록합니다(`cache.tagquery_cache_path` 로 변경 가능).
- 스냅샷은 CRC32 체크섬을 저장해 손상 여부를 감지하고, 드라이런/백테스트가 동일한 큐 세트를 재생하도록 보장합니다.

## 타이밍 & 타임아웃

- HTTP 타임아웃: `qmtl.runtime.sdk.runtime.HTTP_TIMEOUT_SECONDS` (기본 2.0초; 테스트에서는 1.5초).
- WebSocket 수신 타임아웃: `qmtl.runtime.sdk.runtime.WS_RECV_TIMEOUT_SECONDS` (기본 30초; 테스트 5초).
- 재조정 폴링 간격: `qmtl.runtime.sdk.runtime.POLL_INTERVAL_SECONDS` (기본 10초; 테스트 2초).
- 테스트 모드: `qmtl.yml` 에 `test.test_mode: true` 를 지정하면 CI 및 로컬 테스트에 보수적인 시간 예산이 적용됩니다.

{{ nav_links() }}

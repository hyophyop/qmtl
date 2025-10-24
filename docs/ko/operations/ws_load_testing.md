# WebSocket 부하 및 내구성

Gateway의 WS 브리지는 ControlBus 업데이트를 SDK로 릴레이합니다. 이 문서는 목표 처리율, 벤치마크 방법, 운영 설정을 정리합니다.

## 목표

- 지속 처리율: 정상 경로에서 손실 없이 분당 10,000 이벤트 이상(초당 약 167 메시지)
- 토픽별 순서: Gateway 팬아웃 루프 내에서 최선 노력으로 유지
- 백프레셔: 과부하 시 동작하며 최신 이벤트를 드롭할 수 있고 카운터가 증가

## 벤치마크 방법(개발 환경)

- 구독자: `/ws/evt` 에 유효 토큰으로 연결된 인프로세스 더미 웹소켓 100개
- 토픽: `activation`, `queue`
- 부하: 5분 동안 180 msg/s, 이후 1분 동안 600 msg/s
- 관찰 메트릭:
  - `event_relay_events_total{topic="activation"}` 이 정상 비율로 선형 증가
  - `event_relay_dropped_total{topic}` 은 180 msg/s 이하에서 0, 600 msg/s에서 증가
  - `ws_subscribers{topic}` 이 예상 구독자 수와 일치하고 `ws_dropped_subscribers_total` 은 0 유지

## 운영 메모

- 멱등성: CloudEvents `id` 는 멱등 키로 사용됩니다. WS 허브는 고정 크기(10,000개)의 윈도우를 유지해 재연결/재시도 중 중복을 제거합니다.
- 백프레셔 정책: 내부 팬아웃 큐는 제한(기본 10k)되어 있습니다. 큐가 가득 차면 최신 이벤트를 드롭하고 `event_queue_full_drop` 구조화 로그를 남깁니다.
- 순서: 단일 프로세스 허브에서는 토픽별 순서가 최선 노력으로 유지됩니다. 업스트림에서 파티션 간 재정렬 가능성이 있다면 소비자는 `time` 또는 CloudEvent에 포함된 단조 증가 `seq_no` 를 사용해 재조립해야 합니다.
- 스코핑: 서버 측 필터는 JWT의 `world_id`, 선택적 `strategy_id` 를 적용해 월드 간 이벤트 누수를 방지합니다.

### 복구 & 멱등성

- WS 전용 러너는 일시적 연결 끊김 후에도 중복 상태 변경 없이 복구합니다.
  - 서버는 슬라이딩 윈도우 내에서 CloudEvent `id` 중복을 제거합니다.
  - SDK는 `(tags, interval, match_mode)` 키 단위로 `queue_update` 페이로드가 기존 큐 집합과 동일하면 중복을 무시합니다.
- 소비자는 WS 메시지를 변동 트리거가 아닌 상태 업데이트로 취급하고, 재연결 시 중복 업데이트를 무시하고 그대로 진행해야 합니다.

### 레이트 리미팅

- WS 허브에는 단순 토큰 버킷 기반 연결별 레이트 리미팅이 있습니다. 기본값은 비활성입니다. 활성화하려면 Gateway YAML에서 `gateway.websocket.rate_limit_per_sec` 를 설정하세요(초당 토큰/메시지, 예: `gateway.websocket.rate_limit_per_sec: 200`).

## 트러블슈팅

- 드롭이 잦다: 큐 크기를 늘리거나 게시 속도를 낮추세요. 소비자 ack가 제때인지 확인합니다.
- 메모리 증가: 구독자가 정상 종료하는지 확인하고 `ws_dropped_subscribers_total`, GC 로그를 점검하세요.
- 인증 실패: `ws_auth_failed`, `ws_token_refreshed` 로그를 확인하고 `/events/jwks` 에서 JWKS가 노출되는지 검증하세요.

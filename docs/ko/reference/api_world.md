---
title: "World API 레퍼런스 — Gateway 프록시"
tags: [reference, api, world]
author: "QMTL Team"
last_modified: 2025-09-22
---

{{ nav_links() }}

# World API 레퍼런스 — Gateway 프록시

Gateway는 SDK와 도구를 위해 WorldService 엔드포인트를 프록시합니다. 여기서는 핵심 엔드포인트와 표준 엔벌로프를 정리합니다. 예시는 `docs/ko/world/world.md` 12장을 참고하세요.

## 인증

- 외부 호출자는 Gateway(JWT)에 인증합니다. Gateway는 서비스 자격 증명으로 WorldService에 인증/인가를 수행하고, 아이덴티티 스코프를 전달합니다.

## 엔드포인트

### GET /worlds/{id}
월드 메타데이터와 기본 정책 버전을 반환합니다.

### GET /worlds/{id}/decide
지정한 `as_of`에 대한 DecisionEnvelope을 반환합니다.

쿼리 파라미터
- `as_of` (선택 ISO‑8601). 생략 시 서버 시간이 사용됩니다.

응답 (DecisionEnvelope)
```json
{
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "effective_mode": "validate",
  "reason": "data_currency_ok&gates_pass&hysteresis",
  "as_of": "2025-08-28T09:00:00Z",
  "ttl": "300s",
  "etag": "w:crypto_mom_1h:v3:1724835600"
}
```
스키마: reference/schemas/decision_envelope.schema.json

### POST /worlds/{id}/decisions
해당 월드에 대한 활성 전략 집합을 대체합니다. 페이로드는 `DecisionsRequest`이며 `qmtl.services.worldservice.schemas.DecisionsRequest`와 동일한 계약을 따릅니다.

요청 (DecisionsRequest)
```json
{
  "strategies": ["alpha", "beta"]
}
```

의미

- `strategies` 는 비어 있지 않은 문자열 리스트여야 합니다. 공백을 제거한 뒤 순서를 유지한 채 중복이 제거됩니다.
- 빈 리스트를 제공하면 월드의 활성 전략 결정을 모두 비웁니다.
- 응답은 `/worlds/{id}/bindings` 와 동일한 엔벌로프를 사용해 저장된 전략 목록을 그대로 반환합니다.

응답 (BindingsResponse)
```json
{
  "strategies": ["alpha", "beta"]
}
```

스키마: reference/schemas/decisions_request.schema.json

### GET /worlds/{id}/activation
전략/사이드별 활성화를 반환합니다.

쿼리 파라미터
- `strategy_id` (문자열), `side` ("long"|"short")

응답 (ActivationEnvelope)
```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "effective_mode": "paper",
  "execution_domain": "dryrun",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z"
}
```
`effective_mode` 는 WorldService 정책 문자열을 담으며 기존 호환성을 유지합니다 (`validate|compute-only|paper|live`). WorldService ActivationEnvelope 원본 스키마에는 파생 필드인 `execution_domain` 이 없지만, Gateway 프록시는 다음 규칙을 적용해 값을 추가합니다: `validate → backtest (주문 차단)`, `compute-only → backtest`, `paper → dryrun`, `live → live`. `shadow` 는 운영자가 제어하는 듀얼 런을 위해 예약되어 있습니다. SDK는 이 매핑을 로컬 상태/메트릭을 위한 읽기 전용 주석으로 취급해야 하며, 백엔드 결정을 덮어쓰거나 클라이언트 실행 동작을 변경해서는 안 됩니다.
스키마: reference/schemas/activation_envelope.schema.json

### GET /worlds/{id}/{topic}/state_hash
지정한 토픽의 `state_hash` 를 반환해 전체 스냅샷 요청 전 편차를 확인할 수 있습니다.

예: `/worlds/{id}/activation/state_hash`

응답
```json
{ "state_hash": "blake3:..." }
```

### POST /worlds/{id}/evaluate
현재 정책을 평가하고 플랜을 반환합니다. 읽기 전용이며 상태를 바꾸지 않습니다.

요청
```json
{ "as_of": "2025-08-28T09:00:00Z" }
```

응답 (예시)
```json
{ "topk": ["s1","s2"], "promote": ["s1"], "demote": ["s9"], "notes": "..." }
```

### POST /worlds/{id}/apply
2단계 Apply 프로세스로 활성화 플랜을 적용합니다.

요청
```json
{ "run_id": "...", "plan": { "activate": ["s1"], "deactivate": ["s9"] } }
```

응답
```json
{
  "ok": true,
  "run_id": "...",
  "active": ["s1", "s2"],
  "phase": "completed"
}
```

- `ok` 는 기본값이 `true`이며 실행이 중단될 때만 `false` 로 전환됩니다.
- `active` 는 Apply 완료 후 저장된 전략 목록을 항상 그대로 반환합니다(없으면 빈 리스트).
- `phase` 는 선택이며, 존재할 경우 최종 단계(`completed`, `rolled_back` 등)를 나타냅니다. 폴링 중에는 `freeze`, `switch` 와 같은 중간 단계가 관찰될 수 있습니다.

### POST /events/subscribe
활성화/큐/정책과 같은 실시간 제어 이벤트를 위한 스트림 디스크립터를 반환합니다.

요청
```json
{ "world_id": "crypto_mom_1h", "strategy_id": "...", "topics": ["activation", "queues"] }
```

응답
```json
{ "stream_url": "wss://gateway/ws/evt?ticket=...", "token": "<jwt>", "topics": ["activation"], "expires_at": "...", "fallback_url": "wss://gateway/ws" }
```
초기 메시지는 반드시 토픽별 전체 스냅샷을 포함하거나 `state_hash` 를 제공해야 합니다. 토큰은 짧은 수명의 JWT이며 클레임에는 `aud`, `sub`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp` 가 포함됩니다. 키 ID(`kid`)는 JWT 헤더로 전달됩니다.

하트비트와 ACK
- 클라이언트는 주기적으로 하트비트를 전송해야 합니다. 어떤 메시지든 전송하면 하트비트로 간주되며, `{ "type": "ack", "last_id": "<cloudevents id>" }` 형태로 명시적 ACK를 보낼 수도 있습니다.
- Gateway는 연결/인증 실패, 재시도, 정상 종료를 구조화된 필드로 로깅하고 `/metrics`에 카운터를 노출합니다.

스코프 필터링
- 구독은 `world_id` 와 `topics` 로 범위가 제한됩니다. WS 브리지는 서버 측에서 필터링을 적용해 권한 있는 월드만 이벤트를 전달합니다.

백프레셔와 레이트 리미트
- Gateway는 내부 팬아웃 큐에 백프레셔를 적용합니다. 부하가 지속되면 최신 메시지가 드롭될 수 있으며 카운터가 증가합니다. 정상 상태에서는 드롭을 0으로 유지하는 것이 목표입니다.
- 클라이언트는 CloudEvents `id`(멱등 키)와 `correlation_id` 를 활용해 재시도 및 멱등 처리를 구현해야 합니다.

순서 및 손실 보장
- 이벤트는 토픽별 순서를 가능한 한 유지합니다. 파티션 간 재정렬이 발생할 가능성이 있다면 소비자는 `time` 또는 단조 증가 `seq_no` 를 이용해 재조합해야 합니다. 정상 경로에서 Gateway는 손실이 없음을 문서화하며, 스냅샷/상태 해시는 복구를 지원합니다.

### GET /events/jwks
이벤트 스트림 토큰을 서명하는 현재/이전 키를 담은 JWKS 문서를 반환합니다.

응답 (예시)
```json
{
  "keys": [
    { "kty": "oct", "use": "sig", "alg": "HS256", "kid": "old", "k": "czE=" },
    { "kty": "oct", "use": "sig", "alg": "HS256", "kid": "new", "k": "czI=" }
  ]
}
```

## 오류 의미

- 404: 존재하지 않는 월드
- 409: 활성화 적용 충돌(etag/run_id 불일치)
- 503: Gateway 일시 저하; 백오프로 재시도 필요

{{ nav_links() }}

### GET /events/schema
WebSocket CloudEvent 엔벌로프의 JSON 스키마를 토픽별로 반환합니다.

응답 (예시)
```json
{ "queue_update": { "$schema": "https://json-schema.org/...", ... }, "activation_updated": { ... } }
```

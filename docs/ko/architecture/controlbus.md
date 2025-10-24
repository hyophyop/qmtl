---
title: "ControlBus — 내부 제어 버스 (SDK에 비공개)"
tags: [architecture, events, control]
author: "QMTL Team"
last_modified: 2025-08-29
---

{{ nav_links() }}

# ControlBus — 내부 제어 버스

ControlBus는 핵심 서비스에서 Gateway로 제어 플레인 업데이트(데이터가 아닌)를 배포합니다. 내부 전용 컴포넌트이며 공개 API가 아닙니다. 기본 배포에서는 SDK가 직접 연결하지 않습니다. 모든 제어 이벤트는 버전이 명시된 봉투 형태이며 `type`, `version` 필드를 포함합니다.

## 0. 역할과 비목표(Non‑Goals)

역할
- ActivationUpdated, PolicyUpdated, QueueUpdated 이벤트의 팬아웃 전달
- 키 보존 순서를 위해 `world_id` 또는 `(tags, interval)` 단위의 파티션 스트림
- 지연 구독자를 위한 압축(compaction) 기반 제한 보관(retention)

비목표
- 단일 진실 소스(SSOT)가 아님: 의사결정/활성화는 WorldService, 큐는 DAG Manager가 보유
- 범용 데이터 버스가 아님: 시세/인디케이터/체결 데이터는 DAG Manager가 관리하는 데이터 토픽에 남김

!!! note "설계 의도"
- 기본적으로 SDK에는 불투명(opaque)합니다. 클라이언트는 Gateway의 토큰화된 WebSocket 브리지(`/events/subscribe`)를 통해서만 제어 이벤트를 구독합니다. 이를 통해 버스를 사설로 유지하고 인증/인가를 중앙화하며, 내부 토픽을 노출하지 않고도 초기 스냅샷/`state_hash` 동기화를 수행할 수 있습니다.

---

## 1. 토폴로지와 의미론

- 전송: Kafka/Redpanda 권장, 동등한 pub/sub 가능; 네임스페이스는 `control.*`
- 토픽(예)
  - `control.activation` — 파티션 키: `world_id`
  - `control.queues` — 파티션 키: `hash(tags, interval)`
  - `control.policy` — 파티션 키: `world_id`
- 순서 보장: 파티션 내부에서만 보장; 컨슈머는 중복 및 간헐적 공백을 처리해야 함
- 전달 보장: 적어도 한 번(at‑least‑once); `etag`/`run_id`로 아이템포턴시 구현

---

## 2. 이벤트 스키마

ActivationUpdated (버전 관리됨)
```json
{
  "type": "ActivationUpdated",
  "version": 1,
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z",
  "state_hash": "blake3:..."
}
```

QueueUpdated (버전 관리됨)
```json
{
  "type": "QueueUpdated",
  "version": 1,
  "tags": ["BTC", "price"],
  "interval": 60,
  "queues": ["q1", "q2"],
  "etag": "q:BTC.price:60:77",
  "ts": "2025-08-28T09:00:00Z"
}
```

PolicyUpdated (버전 관리됨)
```json
{
  "type": "PolicyUpdated",
  "version": 1,
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "checksum": "blake3:...",
  "status": "ACTIVE",
  "ts": "2025-08-28T09:00:00Z"
}
```

---

## 3. 보관 정책과 QoS

- 보관: 짧게(예: 1–24시간), 키 기준 compaction 적용; 재연결/재생(replay)에 충분한 수준
- QoS 분리: `control.*` 토픽을 데이터 토픽과 분리하고, 적절한 쿼터를 강제
- 속도 제한: 느린 컨슈머에 백프레셔 적용; 지연(lag) 지표를 노출

---

## 4. 보안

- 클러스터 사설; 기본적으로 SDK의 직접 접근 금지
- 퍼블리셔/컨슈머에 서비스 인증(mTLS/JWT)
- 토픽 네임스페이스 및 컨슈머 그룹 단위의 인가; 테넌트/월드 범위를 컨슈머 그룹으로 강제

---

## 5. 가시성(Observability)

메트릭
- `controlbus_publish_latency_ms`, `fanout_lag_ms`, `dropped_subscribers_total`
- `replay_queue_depth`, `partition_skew_seconds`

런북
- 컨슈머 그룹 재생성, 월드 수 증가에 따른 파티션 증설, Gateway/WorldService/DAG Manager의 HTTP 동기화(reconcile) 엔드포인트를 통한 백필

---

## 6. 통합 패턴

- WorldService는 ActivationUpdated/PolicyUpdated를 발행합니다.
- DAG Manager는 QueueUpdated를 발행합니다.
- Gateway 인스턴스는 ControlBus를 구독하고 업데이트를 불투명(opaque) WebSocket 스트림(`/events/subscribe`)을 통해 SDK로 중계합니다.

---

## 7. 초기 스냅샷과 위임 WS(선택)

- 초기 스냅샷: 각 토픽의 첫 메시지는 전체 스냅샷이거나 `state_hash`를 포함해야 합니다. 클라이언트는 전체 GET 없이도 수렴 여부를 확인할 수 있습니다.
- 클라이언트는 스냅샷을 가져오기 전 Gateway의 `/worlds/{id}/{topic}/state_hash`로 분기(divergence) 여부를 점검할 수 있습니다.
- 위임 WebSocket(피처 플래그): Gateway는 ControlBus 앞단의 전용 이벤트 스트리머 계층을 가리키는 `alt_stream_url`을 반환할 수 있습니다.
  - 토큰은 단수명의 JWT이며 다음 클레임을 가집니다: `aud=controlbus`, `sub=<user|svc>`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp`. 키 식별자(`kid`)는 JWT 헤더에 포함됩니다.
  - 스트리머는 JWKS/클레임을 검증하고 ControlBus에 브릿지합니다. 기본 배포에서는 비활성화 상태입니다.

{{ nav_links() }}

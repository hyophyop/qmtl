---
title: "ControlBus — 내부 제어 버스 (SDK에 비공개)"
tags: [architecture, events, control]
author: "QMTL Team"
last_modified: 2025-11-12
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

!!! warning "배포 프로파일"
- **prod**: ControlBus는 필수입니다. 브로커/토픽이 없거나 Kafka 클라이언트를 사용할 수 없는 경우 Gateway, WorldService, DAG Manager가 즉시 종료합니다.
- **dev**: 로컬 실행 시 ControlBus를 끌 수 있습니다. 퍼블리셔/컨슈머가 경고를 남기고 I/O를 건너뛰므로 제어 이벤트가 생성되거나 소비되지 않습니다.

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
  "freeze": false,
  "drain": false,
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z",
  "state_hash": "blake3:...",
  "phase": "unfreeze",
  "requires_ack": true,
  "sequence": 17
}
```

- `phase`는 [`freeze`, `unfreeze`] 중 하나이며 WorldService의 [`ActivationEventPublisher.update_activation_state`]({{ code_url('qmtl/services/worldservice/activation.py#L58') }})에서 설정된다.
- `requires_ack=true` 이벤트는 Gateway가 동일 run의 Freeze/Unfreeze 상태를 수신했음을 ControlBus 응답 채널을 통해 확인(ack)해야 함을 의미한다(SHALL). ACK가 도착하기 전까지 Gateway/SDK는 주문 게이트를 해제할 수 없다.
- `sequence`는 [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }})에서 생성되는 run별 단조 증가 값이다. 컨슈머는 증가 순서를 강제하고 누락된 시퀀스가 감지되면 재동기화를 시도해야 한다(SHOULD).

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

## 3-A. Activation ACK 응답 경로

- Freeze/Unfreeze 이벤트마다 Gateway는 최신 `sequence`와 연관된 ACK 메시지를 ControlBus(예: `control.activation.ack`) 또는 동일하게 구성된 응답 채널로 게시해야 한다(SHALL). 메시지에는 최소한 `world_id`, `run_id`, `sequence`가 포함되어야 하며, 운영팀이 재동기화 상태를 판단할 수 있어야 한다.
- WorldService 및 운영 도구는 ACK 스트림을 모니터링하여 누락된 시퀀스나 타임아웃을 감지하고 필요 시 Apply를 중단·롤백한다(SHOULD).
- Gateway는 SDK/WebSocket 구독자로부터 하위 ACK가 누락된 경우 ControlBus ACK 전송을 보류해 freeze 상태가 유지되도록 해야 한다.

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

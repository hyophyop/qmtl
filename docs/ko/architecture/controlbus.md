---
title: "ControlBus — 내부 제어 버스 (SDK에 비공개)"
tags: [architecture, events, control]
author: "QMTL Team"
last_modified: 2026-02-06
spec_version: v1.0
---

{{ nav_links() }}

# ControlBus — 내부 제어 버스

관련: [WorldService](worldservice.md)  
관련: [ACK/Gap Resync RFC (초안)](ack_resync_rfc.md)

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

- 전송: Kafka/Redpanda 권장, 동등한 pub/sub 가능. 토픽명은 배포/서비스 구성에서 주입되며 네임스페이스는 `control.*`를 권장합니다.
- 토픽(예: Gateway가 구독하는 분리형 토픽 구성)
  - `activation` — 파티션 키: `world_id`
  - `control.activation.ack` — 파티션 키: `world_id` (Activation ACK 응답)
  - `queue` — 파티션 키: `",".join(tags)` (Gateway가 태그 조합별 순서를 유지)
  - `policy` — 파티션 키: `world_id`
  - `sentinel_weight` — 파티션 키: `sentinel_id`
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
- `requires_ack=true` 이벤트는 Gateway가 `(world_id, run_id)` 기준 연속 시퀀스만 적용하고, 적용 완료된 각 `sequence`에 대해 `control.activation.ack`로 ACK를 게시해야 함을 의미한다(SHALL). 이 ACK는 Gateway 수신/적용 확인이며, 모든 하위 SDK/WebSocket 소비자까지의 종단 ACK나 주문 경로 재개 완료를 뜻하지 않는다.
- `sequence`는 [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }})에서 생성되는 run별 단조 증가 값이다. 현재 Gateway 컨슈머는 `sequence < next_sequence`를 중복으로 드롭하고, `sequence > next_sequence`는 버퍼링한 뒤 누락 구간이 채워질 때까지 ACK/릴레이를 보류하며, `sequence == next_sequence`가 들어오면 연속 버퍼를 순차 플러시한다.

ActivationAck (버전 관리됨)
```json
{
  "type": "ActivationAck",
  "version": 1,
  "world_id": "crypto_mom_1h",
  "run_id": "7a1b4c...",
  "sequence": 17,
  "phase": "unfreeze",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "ts": "2025-08-28T09:00:00Z",
  "ack_ts": "2025-08-28T09:00:00Z",
  "idempotency_key": "activation_ack:crypto_mom_1h:7a1b4c...:17:unfreeze:1"
}
```

- `ActivationAck`는 Gateway가 `ActivationUpdated.requires_ack=true` 이벤트를 수신한 뒤 응답 채널(예: `control.activation.ack`)로 게시하는 확인 메시지다.
- 파티션 키는 `world_id`이며, 동일 월드 내에서 `sequence` 증가 순서를 유지해야 한다.
- 컨슈머는 `idempotency_key` 또는 `(world_id, run_id, sequence, phase)` 조합으로 중복을 제거해야 한다.

QueueUpdated (버전 관리됨)
```json
{
  "type": "QueueUpdated",
  "version": 1,
  "tags": ["BTC", "price"],
  "interval": 60,
  "queues": [
    {"queue": "q1", "global": false},
    {"queue": "q2", "global": true}
  ],
  "match_mode": "any",
  "etag": "q:BTC.price:60:1",
  "idempotency_key": "queue_updated:BTC.price:60:any:1",
  "ts": "2025-08-28T09:00:00Z"
}
```

SentinelWeightUpdated (버전 관리됨)
```json
{
  "type": "SentinelWeightUpdated",
  "version": 1,
  "sentinel_id": "s_123",
  "weight": 0.25,
  "sentinel_version": "v1.2.3",
  "world_id": "crypto_mom_1h",
  "etag": "sw:s_123:v1.2.3:0.250000:1",
  "ts": "2025-08-28T09:00:00Z",
  "idempotency_key": "sentinel_weight_updated:s_123:v1.2.3:0.250000:1"
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

- Freeze/Unfreeze 이벤트(`requires_ack=true`)마다 Gateway는 해당 이벤트가 연속 시퀀스로 적용된 뒤 `ActivationAck`를 ControlBus 응답 채널(예: `control.activation.ack`)로 게시한다(SHALL). 메시지에는 최소한 `world_id`, `run_id`, `sequence`가 포함되어야 하며, 운영팀이 재동기화 상태를 판단할 수 있어야 한다.
- `requires_ack=true`인데 `sequence`가 없거나 정수가 아니면 메시지를 드롭하고(`event_relay_dropped_total` 증가) ACK를 게시하지 않는다.
- 누락 시퀀스 gap이 있는 경우(`sequence > next_sequence`) 현재 구현은 해당 메시지를 버퍼링하고 ACK/릴레이를 보류한다. Gateway 컨슈머 내부에는 gap timeout 또는 강제 resync 로직이 내장되어 있지 않으므로, 누락 메시지가 도착하거나 프로세스가 재시작될 때까지 대기한다.
- 따라서 timeout 임계치, 경보, 강제 resync(HTTP snapshot/state_hash reconcile), apply 중단/롤백 판단은 WorldService/운영 도구의 외부 정책으로 처리한다(SHOULD). 현재 구현의 apply 완료는 ACK 스트림 수렴을 하드 게이트로 차단하지 않는다. 기본 운영 가이드는 [ACK/Gap Resync RFC (초안)](ack_resync_rfc.md)에서 관리한다.

---

## 4. 보안

- 클러스터 사설; 기본적으로 SDK의 직접 접근 금지
- 퍼블리셔/컨슈머에 서비스 인증(mTLS/JWT)
- 토픽 네임스페이스 및 컨슈머 그룹 단위의 인가; 테넌트/월드 범위를 컨슈머 그룹으로 강제

---

## 5. 가시성(Observability)

메트릭
- Gateway(ControlBus 소비/ACK): `controlbus_lag_ms`, `controlbus_apply_ack_total`, `controlbus_apply_ack_latency_ms`
- Gateway(WebSocket 팬아웃): `event_fanout_total`, `ws_dropped_subscribers_total`, `ws_connections_total`
- DAG Manager(큐 지연): `queue_lag_seconds`, `queue_lag_threshold_seconds`

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
- 클라이언트는 스냅샷을 가져오기 전 Gateway의 `/worlds/{world_id}/{topic}/state_hash`로 분기(divergence) 여부를 점검할 수 있습니다.
- 위임 WebSocket(피처 플래그): Gateway는 ControlBus 앞단의 전용 이벤트 스트리머 계층을 가리키는 `alt_stream_url`을 반환할 수 있습니다.
  - 토큰은 단수명의 JWT이며 다음 클레임을 가집니다: `aud=controlbus`, `sub=<user|svc>`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp`. 키 식별자(`kid`)는 JWT 헤더에 포함됩니다.
  - 스트리머는 JWKS/클레임을 검증하고 ControlBus에 브릿지합니다. 기본 배포에서는 비활성화 상태입니다.

{{ nav_links() }}

# ControlBus/큐 운영 표준

이 문서는 ControlBus(Kafka) 기반 워커/프로듀서가 **idempotent + 관측 가능 + 재처리 가능**하도록 토픽·컨슈머 그룹·재시도/DLQ·dedupe 규칙을 운영 표준으로 정리합니다.

## 토픽/이벤트 타입

- WorldService는 `worldservice.server.controlbus_topic`(기본값: `policy`)에 **CloudEvents** 메시지를 발행/소비합니다.
- 동일 토픽에 여러 이벤트 타입이 공존할 수 있으며, 필터링 기준은 CloudEvents의 `type` 입니다.
  - 예: `risk_snapshot_updated`, `policy_updated`, `activation_updated`, `evaluation_run_created`, `evaluation_run_updated`

## 컨슈머 그룹 (권장)

- RiskHub 스냅샷 소비자: `worldservice-risk-hub`
  - 이벤트 타입 `risk_snapshot_updated`만 처리합니다.

## 재시도/백오프/DLQ (권장 기본값)

### 소비자(RiskHubControlBusConsumer)
- `max_attempts`: 3
- `retry_backoff_sec`: 0.5
- `dlq_topic`: 운영에서 필요 시 명시적으로 활성화(예: `${controlbus_topic}.dlq`)
  - DLQ 이벤트 타입: `risk_snapshot_updated_dlq`

### 프로듀서(ControlBusProducer/RiskHubClient)
- 프로듀서는 재시도/백오프를 내장하고, 실패 시 로깅/메트릭으로 노출해야 합니다.
- RiskHub snapshot payload가 큰 경우(offload 기준 초과):
  - `covariance_ref`, `realized_returns_ref`, `stress_ref` 형태의 **ref 기반 오프로드**를 우선합니다.

## Idempotency / Dedupe 규칙

### RiskHub 스냅샷
- consumer dedupe 키: `risk_snapshot_dedupe_key(payload)`
  - 구성: `(world_id, version, hash, actor, stage)`
- producer는 아래를 반드시 준수합니다.
  - `provenance.actor`(또는 `X-Actor`) 필수
  - `provenance.stage`(또는 `X-Stage`) 강력 권장(backtest/paper/live 분리)
  - `hash`는 stable hash 규칙으로 계산(재시도 시 동일)

### ControlBus 이벤트(일반)
- CloudEvents `correlation_id`는 동일 작업 단위(예: 동일 EvaluationRun)의 재시도/연쇄 이벤트를 묶는 데 사용합니다.
- 이벤트 `data.idempotency_key`가 제공되면, 소비자는 이를 기준으로 중복 처리를 방지할 수 있어야 합니다.

## 관측(메트릭) 체크리스트

WorldService 내 Prometheus 메트릭(예):

- `risk_hub_snapshot_processed_total{world_id,stage}`
- `risk_hub_snapshot_failed_total{world_id,stage}`
- `risk_hub_snapshot_retry_total{world_id,stage}`
- `risk_hub_snapshot_dlq_total{world_id,stage}`
- `risk_hub_snapshot_dedupe_total{world_id,stage}`
- `risk_hub_snapshot_expired_total{world_id,stage}`

## 리허설 시나리오(필수)

- 중복 이벤트 재처리(dedupe hit) 시 메트릭 증가 확인
- TTL 만료 스냅샷 드롭(expired) 확인
- 처리 실패 → 재시도(backoff) 후 성공/또는 DLQ 라우팅 확인
- stage별(backtest/paper/live)로 메트릭 라벨 분리가 유지되는지 확인


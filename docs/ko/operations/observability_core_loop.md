# 코어 루프 관측성 최소셋

이 문서는 Gateway(GW)·WorldService(WS)·DAG Manager(DM)에서 코어 루프 흐름을
연결할 때 반드시 확인해야 하는 최소 관측성 필드와 조회 위치를 정리합니다.
아키텍처 배경은 [Gateway](../architecture/gateway.md),
[WorldService](../architecture/worldservice.md),
[DAG Manager](../architecture/dag-manager.md) 문서를 참고하세요.

## 최소 공통 필드

다음 필드는 로그/메트릭/트레이스에서 동일한 의미로 취급합니다.

* `world_id`
* `execution_domain`
* `run_id`
* `etag`
* (가능하면) `strategy_id`, `request_id`, `decision_id`

## 로그에서 확인할 위치

| 서비스 | 핵심 이벤트 | 확인 필드 | 참고 포인트 |
| --- | --- | --- | --- |
| GW | `dagmanager_diff_dispatch` | `world_id`, `execution_domain`, `strategy_id` | DAG diff 요청 시작 시점 |
| GW | `activation_update_received` | `world_id`, `run_id`, `etag`, `strategy_id` | ControlBus 활성화 이벤트 수신 |
| GW | `rebalancing_planned_received` | `world_id`, `run_id` | 리밸런싱 플랜 수신 |
| WS | `apply_requested` / `apply_stage_*` | `world_id`, `run_id` | Apply 단계 흐름 |
| WS | `activation_update_published` / `activation_state_update_published` | `world_id`, `run_id`, `etag`, `strategy_id` | 활성화 이벤트 발행 |
| WS | `evaluation_decision_completed` | `world_id`, `run_id`, `strategy_id` | 평가/결정 결과 확정 |
| DM | `diff_request_received` | `world_id`, `execution_domain`, `strategy_id` | DAG diff 요청 수신 |

로그 검색 시에는 `run_id`로 WS/GW를 묶고, `execution_domain`으로 DM/queue 변경 흐름을
연결하면 전체 컨텍스트를 빠르게 복원할 수 있습니다.

## 메트릭에서 확인할 위치

* **WorldService**
  * `world_apply_run_total` (`world_id`, `run_id`, `status`)
  * `world_apply_failure_total` (`world_id`, `run_id`, `stage`)
* **Gateway**
  * `controlbus_apply_ack_total` (`world_id`, `run_id`, `phase`)
  * `controlbus_apply_ack_latency_ms` (`world_id`, `run_id`, `phase`)

메트릭은 실행 흐름의 속도·실패율을 확인하는 용도로 사용하고, 동일한 `run_id`로
로그를 조회해 상세 원인을 추적합니다.

## 트레이싱에서 확인할 위치

* `dagmanager_diff_dispatch` / `diff_request_received` 구간에
  `world_id`, `execution_domain`, `strategy_id` span attribute가 부여됩니다.
* WS 평가/Apply 흐름에서 `world_id`, `run_id`, `strategy_id` span attribute가
  기록되며, 활성화 이벤트 발행 시 `etag`가 추가됩니다.

트레이스에서는 span attribute를 기준으로 동일 `run_id`를 연결해
서비스 경계를 넘는 지연 구간을 파악합니다.

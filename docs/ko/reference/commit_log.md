# 커밋 로그 구성

Gateway는 Kafka를 통해 커밋 로그 레코드를 게시하고 소비할 수 있습니다. 아래 설정은 YAML 구성 파일의 `gateway` 섹션 아래에 위치합니다.

```yaml
gateway:
  commitlog_bootstrap: "localhost:9092"
  commitlog_topic: "commit-log"
  commitlog_group: "gateway-commits"
  commitlog_transactional_id: "gateway-writer"
```

- `commitlog_bootstrap` – 커밋 로그 토픽용 Kafka 부트스트랩 서버입니다.
- `commitlog_topic` – 커밋 로그 레코드를 저장하는 컴팩트 토픽입니다.
- `commitlog_group` – Gateway가 커밋 로그를 처리할 때 사용하는 컨슈머 그룹 ID입니다.
- `commitlog_transactional_id` – 커밋 로그 라이터의 멱등 프로듀서를 위한 트랜잭션 ID입니다.

구성이 완료되면 Gateway는 이벤트 루프 안에서 `CommitLogConsumer`를 시작하고, 중복이 제거된 레코드를 처리 콜백으로 전달합니다. 종료 시에는 컨슈머를 중지하고 라이터 프로듀서를 닫습니다. 프로덕션 배포에서는 Gateway가 제출 이벤트를 안정적으로 기록할 수 있도록 `commitlog_bootstrap`과 `commitlog_topic`을 반드시 지정해야 합니다. 라이터가 비활성화된 경우 CLI가 경고를 출력합니다.

## `gateway.ingest` 제출 레코드

수락된 모든 전략 제출은 요청이 큐에 들어가기 전에 커밋 로그에 기록됩니다. 레코드 값은 ``["gateway.ingest", <timestamp_ms>, <strategy_id>, <payload>]`` 튜플로 인코딩되어 :class:`~qmtl.services.gateway.commit_log_consumer.CommitLogConsumer`와 호환됩니다. 메시지 키는 ``ingest:<strategy_id>`` 로 append-only 특성을 유지합니다.

페이로드 객체는 인입 이벤트를 재생하는 데 필요한 모든 데이터를 포함합니다.

| 필드 | 설명 |
| --- | --- |
| ``event`` | 상수 ``"gateway.ingest"`` 마커 |
| ``version`` | 페이로드 스키마 버전(현재 ``1``) |
| ``strategy_id`` | 제출에 할당된 UUID |
| ``dag_hash`` | Sentinel 삽입 이전에 계산한 DAG의 SHA256 해시 |
| ``dag`` | 저장된 DAG JSON(필요 시 `VersionSentinel` 노드 포함) |
| ``dag_base64`` | 빠른 전송을 위한 ``dag`` 의 Base64 표현 |
| ``node_ids_crc32`` | 클라이언트가 제공한 CRC32 체크섬 |
| ``insert_sentinel`` | Gateway가 Sentinel 노드를 덧붙였는지 여부 |
| ``compute_context`` | ``world_id``, ``execution_domain``, ``as_of``, ``partition``, ``dataset_fingerprint``를 포함하는 정규화된 컴퓨트 컨텍스트입니다. Gateway가 세이프 모드로 다운그레이드될 경우 ``downgraded``, ``downgrade_reason``(공유 ``DowngradeReason`` enum 값), ``safe_mode``가 함께 포함됩니다. |
| ``world_ids`` | 제출과 연관된 고유 월드 식별자 목록 |
| ``world_id`` | 제공된 경우 기본 월드 식별자 |
| ``meta`` | 원본 제출 메타데이터(JSON으로 강제 변환) |
| ``submitted_at`` | Gateway가 생성한 ISO-8601 타임스탬프 |

다운스트림 컨슈머는 이 레코드를 사용해 제출 상태를 복구하거나 재큐잉 전에 클라이언트 메타데이터를 감사(audit)할 수 있습니다.

## `gateway.rebalance` 주문 배치

리밸런싱 제출도 커밋 로그를 재사용하며 튜플 형태는
``["gateway.rebalance", <timestamp_ms>, <batch_id>, <payload>]`` 입니다.
페이로드에는 배치 범위(`per_world`, `global`, `per_strategy`), 관련 월드 ID,
생성된 주문 목록, reduce-only 비율 등의 메트릭이 포함됩니다. 공유 계정
모드일 경우 `shared_account` 플래그가 `true`로 설정되어 다운스트림 서비스가
공유 계정 배치를 구분할 수 있습니다.

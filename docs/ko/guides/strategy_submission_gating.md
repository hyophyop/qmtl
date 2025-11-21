# 전략 제출·게이팅 흐름

로컬 실험(offline)에서 월드 주도 실행, 게이트 반영, 성과 평가까지 한 번에 이어지는 최소 흐름을 정리합니다. 월드 정책·게이트웨이 세부 설계는 [world/world.md](../world/world.md)를 참고하세요.

## 1. 준비물

- 전략 클래스: `Strategy` 하위 타입 (예: `strategies.beta_factory.demo.StrategyCls`)
- Gateway URL + world ID
- 히스토리/백필 경로: 기본값인 `SeamlessDataProvider` 사용 권장 ([history_data_quickstart.md](./history_data_quickstart.md))

## 2. 로컬 검증(offline)

```python
from qmtl.runtime.sdk import Runner
from strategies.beta_factory.demo import StrategyCls

Runner.offline(
    StrategyCls,
    history_start=1700000000,
    history_end=1700003600,
    # 필요 시 데이터 직접 주입
    # data=my_seamless_provider,
)
```

- 게이트웨이 없이 DAG/노드 스키마와 히스토리 워머프를 검증합니다.
- `data=`를 주면 StreamInput의 history_provider가 없는 노드에 Seamless 프로바이더를 자동 부착합니다.

## 3. 월드 제출(run)

### CLI (권장)

```bash
qmtl tools sdk run \
  --world-id my-world \
  --gateway-url http://gateway:8080 \
  --strategy path.to.StrategyCls
```

### Python API

```python
Runner.run(
    StrategyCls,
    world_id="my-world",
    gateway_url="http://gateway:8080",
)
```

- Runner는 WorldService 결정을 받아 `effective_mode`(validate/backtest/live 등)를 설정하고, 주문 게이트 상태를 반영합니다.
- 히스토리 범위를 명시하려면 `history_start`/`history_end`를 넘깁니다. 미지정 시 월드/프로바이더 커버리지 기반 기본값을 사용합니다.

## 4. 게이트/활성화 반영

- **ActivationManager**: WorldService가 유지하는 활성 테이블을 SDK에 전달해 주문 발동 여부를 제어합니다.
  - Gateway API: `GET /worlds/{world_id}/activation` (가중치/활성 플래그)
  - WS 브로드캐스트: 활성 세트 변경 시 구독 갱신 (선택)
- 주문 앞단에 게이트 노드를 배치하거나, ExecutionDomain이 `validate/backtest`인 경우 주문 제출을 자동 차단하도록 구성합니다.

## 5. 성과·지표 루프

- Runner는 `Runner._postprocess_result` 경로에서 알파 성과 메트릭을 SDK 메트릭으로 내보냅니다. Prometheus 수집을 켜 두면 WorldService가 정책 평가 시 바로 활용할 수 있습니다.
- 전략에서 추가 지표를 노드 출력 또는 커스텀 메트릭으로 발행해도 됩니다. World 정책 DSL(게이트/스코어/제약)에 맞게 지표 이름을 정렬하세요.

## 6. 권장 안전장치

- `schema_enforcement="fail"` 기본값을 유지해 노드 스키마 일관성을 강제합니다.
- 라이브 제출 시 `--allow-live` / world‑scope RBAC를 사용하고, `effective_mode`가 `validate`일 때는 주문이 차단되는지 확인하세요.
- 데이터 통화성/히스토리 커버리지가 부족하면 WorldService가 `validate` 모드로 내릴 수 있습니다. 로그에서 `effective_mode`와 이유를 함께 확인하세요.

## 7. 더 읽기

- 월드 정책/게이트 설계: [world/world.md](../world/world.md)
- 히스토리 데이터 연결: [history_data_quickstart.md](./history_data_quickstart.md)
- 노드/DAG 작성 튜토리얼: [sdk_tutorial.md](./sdk_tutorial.md)

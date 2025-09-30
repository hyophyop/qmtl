# WorldService 스모크 테스트

이 스모크 테스트는 동일 전략을 두 개의 월드에 귀속하여 실행하고,
- 월드별 정책/메트릭/활성화가 분리되는지,
- (서비스 모드일 경우) 이벤트/토픽 네임스페이스가 월드 단위로 분리되는지,
- (SDK 모드일 경우) 동일 전략이라도 월드별 아티팩트·로그가 격리되는지

를 빠르게 확인합니다.

## 준비

- Python 3.10+
- pytest
- (권장) jq, curl
- QMTL 런타임:
  - 서비스 모드: Gateway, DAG Manager, WorldService/ControlBus가 떠 있어야 합니다.
  - SDK 모드: 서비스 없이도 Runner 오프라인 실행으로 최소 검증.

## 실행 모드

- 서비스 모드: ControlBus/WorldService에 붙어서 월드 생성/이벤트 구독/실행 상태를 점검합니다.
- SDK 모드(기본): 서비스가 없을 때 동작. Runner로 동일 전략을 서로 다른 월드로 두 번 실행해 아티팩트 격리·라벨링을 확인합니다.

### 환경 변수

| 변수 | 설명 | 기본값 |
|---|---|---|
| `WS_MODE` | `service` 또는 `sdk` | `sdk` |
| `WORLDS_BASE_URL` | WorldService 베이스 URL (예: http://localhost:8080) |  |
| `GATEWAY_URL` | Gateway 베이스 URL (예: http://localhost:8000) |  |
| `QMTL_METRICS_URL` | Prometheus 형식 메트릭 URL (예: http://localhost:9000/metrics) |  |
| `ARTIFACT_DIR` | SDK 모드 실행 산출물 경로 | `.artifacts/world_smoke` |

## 퀵스타트

### 1) (선택) 서비스 기동
```bash
cd tests/e2e/world_smoke/scripts
./up.sh    # 필요 시 포트/바이너리 경로 수정
```

### 2) pytest 실행

```bash
# SDK 모드 (기본)
pytest -q tests/e2e/world_smoke/test_world_service_smoke.py

# 서비스 모드
WS_MODE=service \
WORLDS_BASE_URL=http://localhost:8080 \
GATEWAY_URL=http://localhost:8000 \
QMTL_METRICS_URL=http://localhost:9000/metrics \
pytest -q tests/e2e/world_smoke/test_world_service_smoke.py
```

### 3) (선택) 종료

```bash
cd tests/e2e/world_smoke/scripts
./down.sh
```

## 기대 결과(요약)

* SDK 모드:

  * `ARTIFACT_DIR/prod-us-equity/...` 와 `ARTIFACT_DIR/sandbox-crypto/...` 가 각각 생성되고,
  * 각 폴더의 `run.json`에 `world_id` 라벨이 다르게 기록되어야 함.
* 서비스 모드:

  * WorldService에 두 월드가 등록되고,
  * ControlBus(`/events/subscribe`)에서 월드별 활성/큐 관련 이벤트가 개별적으로 관찰되며,
  * (설정 시) `QMTL_METRICS_URL`에서 `world_id="prod-us-equity"`, `world_id="sandbox-crypto"` 라벨을 가진 알파/샤프 등 메트릭이 각각 노출.

> 엔드포인트·포트는 환경에 맞게 바꾸세요. 테스트는 엔드포인트 부재 시 자동 SKIP합니다.

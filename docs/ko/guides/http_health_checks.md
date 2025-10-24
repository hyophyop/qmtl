# HTTP 헬스 체크 유틸리티

이 가이드는 `qmtl.foundation.common.health` 에 도입된 헬스 프로빙 헬퍼 사용법을 설명합니다. 헬퍼는 결과 형식, 오류 분류, Prometheus 메트릭을 표준화해 모든 HTTP 헬스 프로브에 동일한 관측값을 제공합니다.

## CheckResult 계약

프로브는 다음 필드를 가진 `CheckResult` 데이터 클래스를 반환합니다.

| 필드 | 설명 |
| --- | --- |
| `ok` | 2xx 응답을 받았을 때 `True`. |
| `code` | `OK`, `CLIENT_ERROR`, `SERVER_ERROR`, `TIMEOUT`, `NETWORK`, `UNKNOWN` 중 하나. |
| `status` | 사용 가능한 경우 HTTP 상태 코드. |
| `err` | 전송 또는 타임아웃 실패 시 예외 메시지. |
| `latency_ms` | 밀리초 단위 경과 시간. |

헬퍼를 사용해 프로브 상태를 계산하세요.

```python
from qmtl.foundation.common.health import probe_http

result = probe_http(
    "https://service.internal/health",
    service="gateway",
    endpoint="/health",
)
if result.ok:
    logger.info("Health probe succeeded", extra=result.__dict__)
else:
    logger.warning("Health probe failed", extra=result.__dict__)
```

비동기 호출자는 동일한 파라미터와 동작을 제공하는 `probe_http_async` 를 사용하세요.

## 노출되는 메트릭

모든 프로브는 다음 Prometheus 메트릭을 갱신합니다.

- `probe_requests_total{service,endpoint,method,result}` – 프로브 결과 카운터
- `probe_latency_seconds{service,endpoint,method}` – 프로브 지연 시간 히스토그램(초 단위)
- `probe_last_ok_timestamp{service,endpoint}` – 마지막 성공 시각(Unix 타임스탬프)을 저장하는 게이지

엔드포인트 라벨은 낮은 카디널리티를 유지하세요(예: `/health`, `/readyz`, `/status/{team}` 등). 사용자 입력이나 쿼리 문자열을 그대로 라벨에 전달하지 마세요.

## 테스트 유틸리티

모든 헬퍼는 선택적 `metrics_registry` 인자를 받습니다. 값을 전달하면 해당 레지스트리에 메트릭이 등록되어 전역 레지스트리를 건드리지 않고 단위 테스트에서 값을 검사할 수 있습니다.

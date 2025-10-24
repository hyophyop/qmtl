# HTTPX 사용 가이드

QMTL은 httpx 0.28.x를 대상으로 하며, 갱신된 ASGI 테스트 API를 활용합니다. 이 문서는 테스트와 예제가 일관되고 향후 변경에도 안전하도록 필요한 패턴을 정리합니다.

## 버전 정책

- 의존성 핀: `httpx>=0.28,<0.29`
- 배경: httpx 0.28에서 컨텍스트 매니지드 `ASGITransport` 등이 도입되었습니다. 0.28.x에 고정해 향후 마이너 릴리스로 인한 예기치 못한 깨짐을 방지합니다.

## ASGI 테스트 패턴(비동기)

`ASGITransport` 의 컨텍스트 매니저 형태와 `AsyncClient` 중첩을 사용하세요.

```python
import httpx

async with httpx.ASGITransport(app=app) as transport:
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status")
        assert resp.status_code == 200
```

컨텍스트 매니저 없이 `ASGITransport(app)` 를 생성하거나 `aclose()` 를 직접 호출하지 마세요. 컨텍스트가 정리를 담당합니다.

## 업스트림 서비스 모킹

임시 서버 대신 테스트에서는 `httpx.MockTransport` 를 선호하세요.

```python
async def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})

transport = httpx.MockTransport(handler)
client = httpx.AsyncClient(transport=transport)
```

## WebSocket

FastAPI/Starlette가 제공하는 WebSocket 엔드포인트를 테스트할 때는 동기 테스트에 `fastapi.testclient.TestClient` 를 계속 사용하고, 주변 비동기 HTTP 상호작용에는 위의 `ASGITransport` 패턴을 적용하세요.

## 마이그레이션 참고(0.28 이전 → 0.28)

- `transport = httpx.ASGITransport(app)` + 수동 `aclose()` 사용처는 위에서 소개한 컨텍스트 매니저 형태로 교체하세요.
- ASGI 앱을 대상으로 할 때는 클라이언트에 `base_url` 이 설정되어 있는지 확인하세요.

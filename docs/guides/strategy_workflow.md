---
title: "Strategy Development and Testing Workflow"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Strategy Development and Testing Workflow

> **실무 개발 가이드 및 체크리스트**
>
> - **관심사 분리(SoC)**: 각 모듈은 단일 책임 원칙을 지키고, 인터페이스로 의존성을 최소화하세요. (자세한 내용은 [architecture.md](../architecture/architecture.md) 참고)
> - **테스트 독립성**: 테스트는 서로 의존하지 않게 작성하고, 실패 시 원인을 쉽게 파악할 수 있도록 명확한 assert와 메시지를 사용하세요.
> - **코딩 규칙**: 전략/노드 구현 시 모듈화, 함수 분리, 주석 및 docstring 작성 등 기본 원칙을 지켜주세요.
> - **트러블슈팅**: 설치/실행/연결 오류 발생 시 [docs/reference/faq.md](../reference/faq.md)와 아래 '자주 발생하는 문제'를 참고하세요.
> - **운영/배포**: 배포 전 테스트, 설정 백업, 롤백 플랜, 모니터링 설정을 반드시 확인하세요. (자세한 내용은 [docs/operations/monitoring.md](../operations/monitoring.md), [docs/operations/canary_rollout.md](../operations/canary_rollout.md) 참고)
> - **폴더/파일 역할 요약**:
>   - `strategy.py`: 전략 진입점, Strategy 클래스 구현
>   - `qmtl.yml`: 환경 및 서비스 연결 설정
>   - `generators/`, `indicators/`, `transforms/`: 사용자 확장 노드 구현
>   - `tests/`: 단위/통합 테스트 코드

---

This guide walks through the typical steps for creating and validating a new QMTL
strategy. It starts with installing the SDK and project initialization and
concludes with running the test suite.

## 0. Install QMTL

Create a virtual environment and install the package in editable mode. The
[README](../../README.md) describes the details, but the basic steps are:

```bash
uv venv
uv pip install -e .[dev]
```

## 1. Initialize a Project

Create a dedicated directory for your strategy and generate the scaffold. List
available templates, then initialize the project with a chosen template and
optional sample data:

```bash
qmtl init --list-templates
qmtl init --path my_qmtl_project --strategy branching --with-sample-data
cd my_qmtl_project
```

The command copies a sample `strategy.py`, a `qmtl.yml` configuration and empty
packages for `generators`, `indicators` and `transforms`. These folders let you
extend the SDK by adding custom nodes.


## 2. Explore the Scaffold

- `strategy.py` – a minimal example strategy using the SDK.
- `qmtl.yml` – sample configuration for the Gateway and DAG Manager.
- `generators/`, `indicators/`, `transforms/` – extension packages where you can
  implement additional nodes.

> **구조 설명:** 각 폴더/파일의 역할은 위 '실무 개발 가이드' 참고.

Run the default strategy to verify that everything works. Offline mode is used
when no external services are configured:

```bash
python strategy.py
```
The scaffolded script uses `Runner.offline()` by default, so no external
services are required. To connect to your environment, update the script to call
`Runner.run(world_id=..., gateway_url=...)`, which follows WorldService decisions
and activation events.

The Gateway proxies the WorldService, and SDKs receive control events over the tokenized WebSocket returned by `/events/subscribe`. Activation and queue updates arrive through this opaque control stream instead of being read directly from Gateway state.

## 2a. Example Run Output

The following snippet demonstrates the results of executing the above commands in a clean
container. After creating the scaffold the directory structure looks like:

```text
$ ls -R my_qmtl_project | head
my_qmtl_project:
generators
indicators
qmtl.yml
strategy.py
transforms
...
```

If the script calls `Runner.run(...)` without a reachable Gateway/WorldService,
the strategy will remain in a safe compute‑only state (order gates OFF) until
the control connection is restored.

> **자주 발생하는 문제**
> - Gateway URL 미지정: `--gateway-url` 인자 추가 또는 `Runner.offline()` 사용
> - 의존성 충돌: `uv pip install -e .[dev]`로 재설치 권장

## 3. Develop Your Strategy

Edit `strategy.py` or create new modules inside the extension packages. Each
strategy subclasses `Strategy` and defines a `setup()` method that wires up
`Node` instances. Useful base classes include `StreamInput`, `TagQueryNode` and
`ProcessingNode`. See [docs/sdk_tutorial.md](sdk_tutorial.md) for a full
introduction to these concepts.

Configuration options such as connection strings live in `qmtl.yml`. The file is
ready for local development but can be adjusted to point at production services.

> **개발 가이드라인**
> - 각 노드는 단일 책임 원칙을 지키고, 인터페이스로만 상호작용하세요.
> - 복잡한 로직은 별도 함수/클래스로 분리하고, 주석과 docstring을 작성하세요.
> - 변경 시 반드시 관련 문서와 테스트를 함께 수정하세요.

## 4. Execute with Worlds

Use `Runner.offline()` for local testing without dependencies. For integrated runs,
switch to `Runner.run(strategy_cls, world_id=..., gateway_url=...)`. Activation and queue
updates are delivered via the Gateway's opaque control stream on the `/events/subscribe`
WebSocket; WS remains the authority for policy and activation.

```bash
# start with built-in defaults
qmtl gw
qmtl dagmanager-server

# or load a custom configuration
qmtl gw --config qmtl/examples/qmtl.yml
qmtl dagmanager-server --config qmtl/examples/qmtl.yml
```

Multiple strategies can be executed in parallel by launching separate processes
or using the `parallel_strategies_example.py` script.

> **Tip:** 운영 환경에서는 `qmtl.yml`의 설정을 반드시 백업하고, 롤백 플랜을 준비하세요.

## 5. Test Your Implementation

Always run the unit tests before committing code:

```bash
uv run -m pytest -W error
```

A sample execution inside the container finished successfully:

```text
======================= 260 passed, 1 skipped in 47.15s ========================
```

End‑to‑end tests require Docker. Start the stack and execute the tests:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
uv run -m pytest tests/e2e
```

For details on the test environment refer to
[docs/operations/e2e_testing.md](../operations/e2e_testing.md). Building wheels can run concurrently with
tests if desired:

```bash
# Example of running wheels and tests in parallel
uv pip wheel . &
uv run -m pytest -W error
wait

### Test Teardown and Shutdown

When a test starts background services (e.g., TagQueryManager subscriptions or ActivationManager), call the shutdown helper in teardown to ensure no lingering tasks or sockets remain:

```python
# sync tests
strategy = Runner.run(MyStrategy, world_id="w", gateway_url="http://gw", offline=True)
try:
    ...  # assertions
finally:
    Runner.shutdown(strategy)

# async tests
strategy = await Runner.run_async(MyStrategy, world_id="w", gateway_url="http://gw")
...
await Runner.shutdown_async(strategy)
```

The helpers are idempotent and safe to call even if no background services are active.

### Test Mode Budgets

Set `QMTL_TEST_MODE=1` when running tests to apply conservative client-side budgets that reduce the chance of hangs in flaky environments:

- HTTP clients: issue explicit status requests and retry on missing ACK rather than relying on short timeouts.
- WebSocket client: rely on application-level heartbeats and ACKs with a bounded retry window instead of receive timeouts.

Example heartbeat loop:

```python
while True:
    await ws.send({"op": "heartbeat"})
    ack = await ws.recv()
    if ack.get("op") != "ack":
        raise RuntimeError("missing ACK")
```

Example:

```bash
export QMTL_TEST_MODE=1
uv run -m pytest -W error
```
```

> **테스트 작성 가이드**
> - 테스트는 독립적으로 작성하고, 다른 테스트에 의존하지 않게 하세요.
> - 실패 시 원인을 쉽게 파악할 수 있도록 assert 메시지를 명확히 작성하세요.
> - 커버리지 기준을 정하고, 주요 로직은 반드시 테스트를 작성하세요.
> - 통합 테스트와 단위 테스트를 구분해 관리하세요.

## 6. Next Steps

Consult [architecture.md](../architecture/architecture.md) for a deep dive into the overall
framework and `qmtl/examples/` for reference strategies. When ready, deploy the
Gateway and DAG Manager using your customized `qmtl.yml`.

> **운영/배포 체크리스트**
> - 테스트 통과 및 커버리지 확인
> - 설정 파일 백업 및 버전 관리
> - 모니터링/알림 설정 ([docs/operations/monitoring.md](../operations/monitoring.md))
> - 점진적 배포/롤백 플랜 ([docs/operations/canary_rollout.md](../operations/canary_rollout.md))
> - 배포 후 주요 로그/지표 확인

> **참고자료**
> - [architecture.md](../architecture/architecture.md): 전체 시스템 구조
> - [sdk_tutorial.md](sdk_tutorial.md): SDK 및 전략 개발 예제
> - [faq.md](../reference/faq.md): 자주 묻는 질문
> - [monitoring.md](monitoring.md): 모니터링 및 운영
> - [canary_rollout.md](canary_rollout.md): 점진적 배포 전략
> - [qmtl/examples/](../qmtl/examples/): 다양한 전략 예제

{{ nav_links() }}

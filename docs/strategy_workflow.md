# Strategy Development and Testing Workflow

> **실무 개발 가이드 및 체크리스트**
>
> - **관심사 분리(SoC)**: 각 모듈은 단일 책임 원칙을 지키고, 인터페이스로 의존성을 최소화하세요. (자세한 내용은 [architecture.md](../architecture.md) 참고)
> - **테스트 독립성**: 테스트는 서로 의존하지 않게 작성하고, 실패 시 원인을 쉽게 파악할 수 있도록 명확한 assert와 메시지를 사용하세요.
> - **코딩 규칙**: 전략/노드 구현 시 모듈화, 함수 분리, 주석 및 docstring 작성 등 기본 원칙을 지켜주세요.
> - **트러블슈팅**: 설치/실행/연결 오류 발생 시 [docs/faq.md](faq.md)와 아래 '자주 발생하는 문제'를 참고하세요.
> - **운영/배포**: 배포 전 테스트, 설정 백업, 롤백 플랜, 모니터링 설정을 반드시 확인하세요. (자세한 내용은 [docs/monitoring.md](monitoring.md), [docs/canary_rollout.md](canary_rollout.md) 참고)
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
[README](../README.md) describes the details, but the basic steps are:

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
- `qmtl.yml` – sample configuration for the Gateway and DAG manager.
- `generators/`, `indicators/`, `transforms/` – extension packages where you can
  implement additional nodes.

> **구조 설명:** 각 폴더/파일의 역할은 위 '실무 개발 가이드' 참고.

Run the default strategy to verify that everything works:

```bash
python strategy.py
```
The scaffolded script invokes `Runner.backtest()` which expects a running
Gateway and DAG manager. Provide a `--gateway-url` argument, or modify the
script to use `Runner.offline()` when testing without external services.

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

Running the default strategy without a Gateway URL produces an error:

```text
$ python strategy.py
RuntimeError: gateway_url is required for backtest mode
```

Provide a `--gateway-url` argument or modify the script to use `Runner.offline()` when running locally.

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

## 4. Execute in Different Modes

Run strategies via the CLI or programmatically with `Runner`.

```bash
python -m qmtl.sdk mypkg.strategy:MyStrategy --mode backtest \
    --start-time 2024-01-01 --end-time 2024-02-01 \
    --gateway-url http://localhost:8000
```

Available modes are `backtest`, `dryrun`, `live` and `offline`. The first three
require a running Gateway and DAG manager. Start them in separate terminals. The
``--config`` flag is optional:

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
[docs/e2e_testing.md](e2e_testing.md). Building wheels can run concurrently with
tests if desired:

```bash
# Example of running wheels and tests in parallel
uv pip wheel . &
uv run -m pytest -W error
wait
```

> **테스트 작성 가이드**
> - 테스트는 독립적으로 작성하고, 다른 테스트에 의존하지 않게 하세요.
> - 실패 시 원인을 쉽게 파악할 수 있도록 assert 메시지를 명확히 작성하세요.
> - 커버리지 기준을 정하고, 주요 로직은 반드시 테스트를 작성하세요.
> - 통합 테스트와 단위 테스트를 구분해 관리하세요.

## 6. Next Steps

Consult [architecture.md](../architecture.md) for a deep dive into the overall
framework and `qmtl/examples/` for reference strategies. When ready, deploy the
Gateway and DAG manager using your customized `qmtl.yml`.

> **운영/배포 체크리스트**
> - 테스트 통과 및 커버리지 확인
> - 설정 파일 백업 및 버전 관리
> - 모니터링/알림 설정 ([docs/monitoring.md](monitoring.md))
> - 점진적 배포/롤백 플랜 ([docs/canary_rollout.md](canary_rollout.md))
> - 배포 후 주요 로그/지표 확인

> **참고자료**
> - [architecture.md](../architecture.md): 전체 시스템 구조
> - [sdk_tutorial.md](sdk_tutorial.md): SDK 및 전략 개발 예제
> - [faq.md](faq.md): 자주 묻는 질문
> - [monitoring.md](monitoring.md): 모니터링 및 운영
> - [canary_rollout.md](canary_rollout.md): 점진적 배포 전략
> - [qmtl/examples/](../qmtl/examples/): 다양한 전략 예제

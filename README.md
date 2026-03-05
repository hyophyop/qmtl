<!-- markdownlint-disable MD013 MD033 -->

> ⚠️ **Warning**: This repository is under active development. Some features
> and APIs may change without notice.

# QMTL

**QMTL**은 트레이딩 전략을 DAG(Directed Acyclic Graph)로 오케스트레이션하는 플랫폼입니다.
전략 작성자는 **전략 로직에만 집중**하고, 시스템이 최적화·평가·배포를 자동으로 처리합니다.

> *"Write strategy → Submit → (System evaluates/deploys) → Observe"*

---

## 📋 Table of Contents

- [Core Loop](#-core-loop)
- [Architecture](#-architecture)
- [Quickstart](#-quickstart)
- [Project Structure](#-project-structure)
- [Optional Modules](#-optional-modules)
- [Development](#-development)
- [Documentation](#-documentation)

---

## 🔄 Core Loop

QMTL의 핵심 워크플로우는 단일 진입점 `Runner.submit(strategy, world=...)`입니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CORE LOOP                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. AUTHOR        2. SUBMIT           3. EVALUATE        4. OBSERVE        │
│   ───────────      ──────────          ───────────        ──────────        │
│   Strategy DAG  →  Runner.submit()  →  WorldService   →   Results/Metrics   │
│   (nodes, data)    (world=...)         (policy/gate)      (activation)      │
│                                                                             │
│   ┌─────────┐      ┌─────────┐         ┌─────────┐        ┌─────────┐       │
│   │ SDK     │ ──→  │ Gateway │ ──→     │ WS/DM   │ ──→    │ Output  │       │
│   │ Strategy│      │ HTTP    │         │ Policy  │        │ Metrics │       │
│   └─────────┘      └─────────┘         └─────────┘        └─────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Loop 원칙

| 원칙 | 설명 |
|------|------|
| **Single Entrypoint** | 모든 제출은 `Runner.submit(..., world=...)` 하나로 통일 |
| **WS as SSOT** | WorldService가 stage/mode 결정의 단일 진실 공급원 (backtest→paper→live) |
| **Default-Safe** | WS 결정이 없거나 stale하면 자동으로 compute-only(backtest)로 다운그레이드 |
| **Data On-Ramp** | World preset이 Seamless 데이터 프로바이더를 자동 연결 |

### 최소 예제

```python
from qmtl.sdk import Strategy, StreamInput, Node, Runner

class MyStrategy(Strategy):
    def setup(self):
        price = StreamInput(tags=["BTC", "price"], interval="1m", period=30)
        
        def compute(view):
            df = view.as_frame(price, columns=["close"])
            signal = (df["close"].pct_change().rolling(5).mean() > 0).astype(int)
            return {"signal": signal}
        
        self.add_nodes([price, Node(input=price, compute_fn=compute, name="signal")])

# Submit & let WorldService decide the execution mode
result = Runner.submit(MyStrategy, world="my_world")
```

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           QMTL SYSTEM                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────┐     ┌─────────────┐     ┌──────────────┐                    │
│  │   SDK   │────▶│   Gateway   │────▶│  DAG Manager │                    │
│  │ Runner  │     │  (HTTP API) │     │  (Graph SSOT)│                    │
│  └─────────┘     └──────┬──────┘     └──────────────┘                    │
│                         │                    │                           │
│                         ▼                    ▼                           │
│                  ┌─────────────┐     ┌──────────────┐                    │
│                  │WorldService │     │  ControlBus  │                    │
│                  │(Policy SSOT)│     │ (Event Bus)  │                    │
│                  └─────────────┘     └──────────────┘                    │
│                         │                    │                           │
│                         ▼                    ▼                           │
│                  ┌─────────────┐     ┌──────────────┐                    │
│                  │Risk Signal  │     │   Workers/   │                    │
│                  │    Hub      │     │   Runners    │                    │
│                  └─────────────┘     └──────────────┘                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 주요 컴포넌트

| 컴포넌트 | 역할 | 위치 |
|----------|------|------|
| **SDK/Runner** | 전략 작성·직렬화·제출 | `qmtl/sdk/`, `qmtl/runtime/sdk/` |
| **Gateway** | 클라이언트 API, 프록시, 캐싱 | `qmtl/services/gateway/` |
| **WorldService** | 정책·평가·활성화 SSOT | `qmtl/services/worldservice/` |
| **DAG Manager** | 그래프·노드·큐 SSOT, Diff | `qmtl/services/dagmanager/` |
| **ControlBus** | 내부 이벤트 버스 (Kafka/WS) | `qmtl/foundation/` |
| **Risk Signal Hub** | 포트폴리오/리스크 스냅샷 | `qmtl/services/` |
| **Seamless Provider** | 데이터 공급 자동화 (v2) | `qmtl/runtime/io/` |

### Execution Domains

| Domain | 설명 |
|--------|------|
| `backtest` | 과거 데이터 리플레이, 주문 게이트 OFF |
| `dryrun` (paper) | 실시간 데이터, 모의 주문 |
| `live` | 실거래, 정책 게이트 통과 필수 |
| `shadow` | 운영자 전용, 병렬 검증 |

---

## 🚀 Quickstart

### 1. 환경 설정

```bash
# uv 사용 (권장)
uv venv
uv pip install -e .[dev]

# 또는 pip
pip install -e .[dev]
```

### 2. 프로젝트 초기화

```bash
qmtl init my_project
cd my_project
```

- 공개 전략 작성자 경로는 `qmtl init`, `qmtl submit`, `qmtl status`, `qmtl world` 입니다.
- 로컬 전략 개발 루프에서는 `strategies/my_strategy.py`를 수정한 뒤 `qmtl submit --output json`로 빠르게 검증할 수 있습니다.

### 3. 예제 실행

```bash
python -m qmtl.examples.general_strategy
```

### 4. 서비스 실행 (선택)

```bash
# 설정 검증
uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline

# Gateway 시작 (operator/admin path)
qmtl --admin gateway --config qmtl/examples/qmtl.yml

# DAG Manager 시작 (operator/admin path)
qmtl --admin dagmanager-server --config qmtl/examples/qmtl.yml

# WorldService 시작
uv run uvicorn qmtl.services.worldservice.api:create_app --factory --port 8080
```

---

## 📁 Project Structure

```
qmtl/
├── sdk/                    # 전략 작성 SDK (Strategy, Node 등)
├── runtime/
│   ├── sdk/               # Runner, submit, execution context
│   ├── io/                # Seamless data provider v2
│   ├── indicators/        # 기술적 지표 (EMA, RSI 등)
│   ├── generators/        # 데이터 생성기
│   └── transforms/        # 데이터 변환
├── services/
│   ├── gateway/           # HTTP API Gateway
│   ├── worldservice/      # Policy/Activation SSOT
│   └── dagmanager/        # Graph/Queue SSOT
├── foundation/            # 공통 기반 (proto, controlbus 등)
├── integrations/          # 외부 시스템 연동
├── examples/              # 예제 전략들
└── cli.py                 # CLI 진입점

docs/
├── en/                    # English docs
└── ko/                    # Korean docs (canonical)
```

---

## 📦 Optional Modules

필요에 따라 추가 모듈을 설치할 수 있습니다:

```bash
# IO 모듈 (추가 데이터 소스)
uv pip install -e .[io]

# 기술적 지표
uv pip install -e .[indicators]

# 데이터 생성기
uv pip install -e .[generators]

# 데이터 변환
uv pip install -e .[transforms]

# Ray 분산 실행
uv pip install -e .[ray]

# 전체 설치
uv pip install -e .[dev,io,indicators,generators,transforms,ray]
```

---

## 🛠 Development

### 테스트

```bash
# 전체 테스트 (병렬)
uv run -m pytest -n auto

# E2E 테스트 (Docker 필요)
docker compose -f tests/docker-compose.e2e.yml up -d
uv run -m pytest tests/e2e
```

### Proto 생성

proto 파일 변경 시:

```bash
uv run python -m grpc_tools.protoc \
  --proto_path=qmtl/foundation/proto \
  --python_out=qmtl/foundation/proto \
  --grpc_python_out=qmtl/foundation/proto \
  qmtl/foundation/proto/dagmanager.proto
```

### CLI 도움말

```bash
qmtl --help
qmtl --help-admin
qmtl config --help
```

---

## 📚 Documentation

| 문서 | 설명 |
|------|------|
| [Architecture](docs/en/architecture/architecture.md) | 시스템 설계 상세 |
| [Core Loop](docs/en/architecture/core_loop_world_automation.md) | Core Loop 자동화 |
| [SDK Tutorial](docs/en/guides/sdk_tutorial.md) | SDK 사용 가이드 |
| [Backend Quickstart](docs/en/operations/backend_quickstart.md) | 서비스 구동 가이드 |
| [Gateway](docs/en/architecture/gateway.md) | Gateway 명세 |
| [WorldService](docs/en/architecture/worldservice.md) | WorldService 명세 |
| [DAG Manager](docs/en/architecture/dag-manager.md) | DAG Manager 명세 |

### i18n

- **Korean (canonical)**: `docs/ko/`
- **English**: `docs/en/`
- MkDocs 빌드: `uv run mkdocs build`

---

## 📄 License

See [LICENSE](LICENSE) for details.

---

## 🔗 Links

- [AGENTS.md](AGENTS.md) — 개발 가이드라인
- [CONTRIBUTING.md](CONTRIBUTING.md) — 기여 가이드
- [CHANGELOG.md](CHANGELOG.md) — 변경 이력
```

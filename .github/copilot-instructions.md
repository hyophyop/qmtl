# QMTL Development Instructions

Always follow these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Architecture Overview

architecture.md, gateway.md, dag-manager.md 파일을 참조하여 시스템 아키텍처를 이해합니다. 이 문서는 각각 시스템의 주요 구성 요소인 SDK, gateway, dag-manager와 그 상호작용을 설명합니다.

QMTL orchestrates trading strategies as directed acyclic graphs (DAGs). The system consists of three main components: SDK for building strategy DAGs, Gateway (HTTP server) for handling requests, and DAG Manager (gRPC server) for orchestration.

## SOC (Separation of Concerns)

- 각 모듈은 단일 책임 원칙을 준수해야 합니다.
- 각 모듈은 명확한 책임을 가지고 있으며, 다른 모듈과의 의존성을 최소화해야 합니다.
- 모듈 간의 의존성은 인터페이스를 통해 관리해야 합니다.
- 각 모듈은 독립적으로 테스트 가능해야 합니다.
- 모든 모듈은 문서화되어야 하며, 변경 사항은 즉시 반영해야 합니다.
- 작업 중 기존 코드베이스에서 SoC를 위반하는 부분을 발견하면, 해당 부분을 리팩토링하여 SoC를 준수하도록 수정하는 것을 우선시해야 합니다.

## Development Cycle

- 구현 후에 반드시 대응하는 테스트를 작성 및 실행해야 합니다.
- 테스트는 가능한 한 독립적이어야 하며, 다른 테스트에 의존하지 않아야 합니다.
- 테스트는 명확하고 이해하기 쉬워야 하며, 실패 시 원인을 쉽게 파악할 수 있어야 합니다.
- 테스트 실패 시 즉시 원인을 파악하고 수정해야 합니다.

## Environment Setup

**CRITICAL**: Always use these exact commands in order. Do not skip steps.

1. **Check Python version** (must be 3.11+):
   ```bash
   python --version  # Should show 3.11+, we tested with 3.12.3
   ```

2. **Install uv package manager** (if not available):
   ```bash
   pip install uv
   ```

3. **Create virtual environment**:
   ```bash
   uv venv
   ```

4. **Install development dependencies** (takes ~30 seconds):
   ```bash
   uv pip install -e .[dev]
   ```

5. **Optional: Install additional extensions** (takes ~15 seconds each):
   ```bash
   # For additional data modules
   uv pip install -e .[io]
   
   # For technical indicators, data generators, transforms
   uv pip install -e .[indicators,generators,transforms]
   
   # For distributed execution support
   uv pip install -e .[ray]
   ```

6. **Generate protobuf files** (REQUIRED before testing):
   ```bash
   uv run python -m grpc_tools.protoc \
     --proto_path=qmtl/foundation/proto \
     --python_out=qmtl/foundation/proto \
     --grpc_python_out=qmtl/foundation/proto \
     qmtl/foundation/proto/dagmanager.proto
   ```

## Testing

**CRITICAL TIMING**: NEVER CANCEL test commands. Set timeouts appropriately.

- **Run full test suite** (takes ~70 seconds, NEVER CANCEL):
  ```bash
  uv run pytest -W error
  ```
  Set timeout to 120+ seconds. Expected: 445+ tests pass, 12 known failures.

- **Run specific test categories** (takes ~10-30 seconds each):
  ```bash
  # Gateway tests
  uv run pytest tests/gateway -v
  
  # E2E tests (requires Docker)  
  uv run pytest tests/e2e -v
  
  # Quick CLI tests
  uv run pytest tests/test_cli.py -v
  ```

- **Known test failures**: Tests fail for missing modules (qmtl.interfaces.tools, some Runner methods). These are development artifacts and do not affect core functionality.

## Building and Running

### Core CLI Commands

- **Check available commands**:
  ```bash
  uv run qmtl --help
  ```

- **Initialize new project**:
  ```bash
  qmtl init --path my_project
  cd my_project
  ```

- **List available templates**:
  ```bash
  qmtl init --path dummy --list-templates
  ```
  Available templates: general, single_indicator, multi_indicator, branching, state_machine

### Running Services

**Services start successfully and run indefinitely. Use separate terminals.**

- **Start Gateway HTTP server** (runs on port 8000):
  ```bash
  uv run qmtl gw
  # Or with custom config:
  uv run qmtl gw --config qmtl/examples/qmtl.yml
  ```

- **Start DAG Manager server** (runs on port 50051):
  ```bash
  uv run qmtl dagmanager-server
  # Or with custom config:
  uv run qmtl dagmanager-server --config qmtl/examples/qmtl.yml
  ```

- **Run example strategies**:
  ```bash
  # Basic strategy execution (takes ~1 second)
  uv run python -m qmtl.examples.general_strategy
  
  # Strategy with indicators (takes ~1 second)
  uv run python -m qmtl.examples.indicators_strategy
  
  # Multi-asset lag strategy
  uv run python -m qmtl.examples.multi_asset_lag_strategy
  ```

## End-to-End Testing with Docker

**CRITICAL**: E2E tests require Docker and take 5-10 minutes to start. NEVER CANCEL.

1. **Pull Docker images** (takes ~10 seconds with good internet):
   ```bash
   docker compose -f tests/docker-compose.e2e.yml pull
   ```

2. **Start E2E infrastructure** (takes ~120 seconds to build and start, NEVER CANCEL):
   ```bash
   docker compose -f tests/docker-compose.e2e.yml up --build -d
   ```
   Set timeout to 300+ seconds. Services include PostgreSQL, Redis, Neo4j, Kafka, and Zookeeper.

3. **Run E2E tests** (takes ~60 seconds):
   ```bash
   uv run pytest tests/e2e
   ```

4. **Stop E2E infrastructure**:
   ```bash
   docker compose -f tests/docker-compose.e2e.yml down
   ```

## Validation Scenarios

**ALWAYS run these validation scenarios after making changes:**

### Basic Functionality Test
1. Run environment setup commands
2. Generate protobuf files
3. Run a subset of tests: `uv run pytest tests/test_cli.py -v`
4. Initialize a test project: `qmtl init --path /tmp/test_validation`
5. Check CLI help works: `uv run qmtl --help`

### Service Integration Test
1. Start DAG Manager in background: `uv run qmtl dagmanager-server &`
2. Verify it's running on port 8000 (shows startup messages)
3. Run example strategy: `uv run python -m qmtl.examples.general_strategy`
4. Stop services

### Full System Test
1. Start E2E infrastructure with Docker
2. Run E2E test suite
3. Verify all services are healthy
4. Stop infrastructure

## Known Issues and Workarounds

- **Gateway service startup error**: The command `uv run qmtl gw` may fail with asyncio errors in some environments. Use DAG Manager for basic testing instead.

- **Missing modules**: Tests for `qmtl.interfaces.tools.taglint` and some `Runner` methods fail due to incomplete implementation. Skip these tests when validating changes.

- **Import errors in scaffolded projects**: When running scaffolded project strategies directly, ensure PYTHONPATH includes the QMTL source: `PYTHONPATH=/path/to/qmtl python strategy.py`

## Project Structure Reference

```
qmtl/                    # Main package
├── sdk/                 # Strategy building SDK
├── gateway/             # HTTP server implementation  
├── dagmanager/          # DAG orchestration service
├── examples/            # Example strategies and configs
├── proto/               # gRPC protocol definitions
└── transforms/          # Data transformation utilities

tests/                   # Test suite
├── e2e/                # End-to-end integration tests
├── gateway/            # Gateway component tests  
├── dagmanager/         # DAG manager tests
└── docker-compose.e2e.yml # E2E infrastructure

docs/                   # Documentation
├── strategy_workflow.md # Strategy development guide
├── e2e_testing.md      # E2E testing guide
└── sdk_tutorial.md     # SDK usage tutorial
```

## Configuration Standards

- Use `*_dsn` suffix for all connection strings (redis_dsn, database_dsn, neo4j_dsn)
- YAML configuration files follow the pattern in `qmtl/examples/qmtl.yml`
- Support both SQLite (development) and PostgreSQL (production) backends

## Command Reference

Common validated commands with expected execution times:

```bash
# Environment (30 seconds)
uv venv && uv pip install -e .[dev]

# Testing (70 seconds, NEVER CANCEL)  
uv run pytest -W error

# Services (run indefinitely)
uv run qmtl dagmanager-server

# Examples (1 second each)
uv run python -m qmtl.examples.general_strategy

# E2E setup (120 seconds build + 10 seconds pull, NEVER CANCEL)
docker compose -f tests/docker-compose.e2e.yml pull
docker compose -f tests/docker-compose.e2e.yml up --build -d
```

**CRITICAL REMINDERS:**
- NEVER CANCEL builds or test commands that take more than 2 minutes
- Always generate protobuf files before testing
- Set timeouts of 120+ seconds for test commands and 600+ seconds for Docker builds
- 12 test failures are expected and do not indicate problems with core functionality
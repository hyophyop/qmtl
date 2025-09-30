# Project Structure

## Root Level Organization

```
qmtl/                    # Main package directory
├── __init__.py          # Package entry point
├── cli.py              # Main CLI entry point with subcommands
├── config.py           # Global configuration management
├── scaffold.py         # Project scaffolding utilities
└── pipeline/           # Core pipeline execution logic

docs/                   # Documentation and guides
├── sdk_tutorial.md     # SDK usage tutorial
├── strategy_workflow.md # Strategy development workflow
├── backfill.md        # Historical data loading guide
├── e2e_testing.md     # End-to-end testing guide
└── dashboards/        # Monitoring dashboard configs

tests/                  # Test suite organization
├── conftest.py        # Shared test fixtures
├── e2e/              # End-to-end integration tests
├── gateway/          # Gateway component tests
├── dagmanager/       # DAG manager tests
└── strategy/         # Strategy execution tests

examples/              # Example strategies and configurations
qmtl.egg-info/        # Package metadata (generated)
```

## Core Package Structure

### SDK (`qmtl/runtime/sdk/`)
Strategy development framework with key modules:
- `strategy.py` - Base Strategy class
- `node.py` - Node types (StreamInput, ProcessingNode, TagQueryNode)
- `runner.py` - Execution engine with backtest/live/dry-run modes
- `cache_view.py` - Read-only data cache interface
- `arrow_cache.py` - PyArrow-based caching implementation
- `tagquery_manager.py` - Dynamic upstream node discovery
- `ws_client.py` - WebSocket client for real-time updates

### Gateway (`qmtl/services/gateway/`)
State management and DAG forwarding service:
- `api.py` - FastAPI HTTP endpoints
- `fsm.py` - Finite state machine for strategy execution
- `dagmanager_client.py` - gRPC client for DAG Manager
- `database.py` - Database abstraction layer
- `redis_client.py` - Redis caching interface
- `worker.py` - Background task processing
- `ws.py` - WebSocket server implementation

### DAG Manager (`qmtl/services/dagmanager/`)
Global DAG storage and queue orchestration:
- `server.py` - gRPC and HTTP server implementation
- `node_repository.py` - Neo4j-based node storage
- `diff_service.py` - DAG comparison and deduplication
- `kafka_admin.py` - Kafka topic management
- `gc.py` - Garbage collection for unused nodes
- `metrics.py` - Prometheus metrics collection

### Extension Modules
- `indicators/` - Technical analysis indicators (RSI, EMA, etc.)
- `generators/` - Market data generators (GARCH, Heston, etc.)
- `transforms/` - Data transformation utilities
- `io/` - Data fetchers and recorders (QuestDB integration)

## Naming Conventions

### Files and Modules
- Use snake_case for Python files and modules
- Prefer descriptive names over abbreviations
- Group related functionality in subpackages

### Variables and Functions
- Use descriptive names, avoid single letters except in short loops
- Prefer `redis_client` over `r`, `dag_manager` over `dm`
- Use `*_dsn` suffix for all connection strings

### Classes and Types
- Use PascalCase for class names
- Suffix abstract base classes with `Base` (e.g., `NodeBase`)
- Use descriptive names for node types (e.g., `StreamInput`, `TagQueryNode`)

## Configuration Organization

### Development vs Production
- `qmtl/examples/qmtl.yml` - Example configuration with SQLite/memory backends
- Production configs should use PostgreSQL, Neo4j, and Kafka
- Environment-specific overrides follow YAML merge patterns

### Service Configuration
Each service (Gateway, DAG Manager) has dedicated config sections:
- Clear separation of concerns
- Consistent DSN naming patterns
- Support for both local and distributed deployments

## Testing Structure

### Test Categories
- Unit tests: Component-specific functionality
- Integration tests: Service interaction testing
- E2E tests: Full system workflow validation
- Performance tests: Load and stress testing

### Test Utilities
- `conftest.py` provides shared fixtures (fake_redis, test databases)
- Docker Compose files for integration test infrastructure
- Separate test configurations for different environments

## Documentation Standards

- README files in each major package directory
- Inline docstrings for public APIs
- Architecture documentation in root-level markdown files
- Example code in dedicated examples directory with execution instructions
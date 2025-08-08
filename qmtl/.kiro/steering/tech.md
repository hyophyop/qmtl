# Technology Stack

## Build System & Package Management

- **Package Manager**: `uv` (preferred) - fast Python package installer and resolver
- **Build System**: setuptools with pyproject.toml configuration
- **Python Version**: >= 3.11 required

## Core Dependencies

- **Web Framework**: FastAPI with uvicorn for HTTP services
- **Async Runtime**: asyncio with asyncpg for PostgreSQL, aiosqlite for SQLite
- **Message Queues**: Kafka/Redpanda with grpcio for DAG Manager communication
- **Caching**: Redis with fakeredis for testing
- **Graph Database**: Neo4j for global DAG storage
- **Data Processing**: pandas, numpy, xarray for time-series operations
- **Distributed Computing**: Ray for parallel execution (optional)
- **Monitoring**: Prometheus client for metrics collection

## Optional Extensions

Install additional functionality on demand:
- `[indicators]` - Technical analysis indicators
- `[io]` - Data fetchers and recorders (pandas, asyncpg)
- `[generators]` - Market data generators
- `[transforms]` - Data transformation utilities
- `[ray]` - Distributed execution support
- `[dev]` - Development and testing dependencies

## Common Commands

### Environment Setup
```bash
# Create virtual environment and install dependencies
uv venv
uv pip install -e .[dev]

# Install with optional extensions
uv pip install -e .[indicators,io,generators,transforms]
```

### Testing
```bash
# Run all tests
uv run -- pytest

# Run specific test categories
uv run -- pytest tests/e2e
uv run -- pytest tests/gateway
```

### Project Initialization
```bash
# Create new QMTL project scaffold
qmtl init --path my_qmtl_project
cd my_qmtl_project
uv pip install -e .[generators,indicators,transforms]
python strategy.py
```

### Service Management
```bash
# Start services with configuration
qmtl gw --config qmtl/examples/qmtl.yml
qmtl dagmgr-server --config qmtl/examples/qmtl.yml

# Submit DAG diff
qmtl dagm diff --file dag.json --target localhost:50051
```

### Example Execution
```bash
# Run example strategies
python -m qmtl.examples.general_strategy
python -m qmtl.examples.strategies.indicators_strategy

# Enable Ray-based parallel execution
python -m qmtl.examples.general_strategy --with-ray
```

### End-to-End Testing
```bash
# Start test infrastructure
docker compose -f tests/docker-compose.e2e.yml up -d

# Run E2E tests
uv run -- pytest tests/e2e
```

## Configuration Standards

- Use `*_dsn` suffix for all connection strings (redis_dsn, database_dsn, neo4j_dsn, kafka_dsn)
- YAML configuration files follow the pattern in `qmtl/examples/qmtl.yml`
- Environment-specific configs should override base settings
- Support both SQLite (development) and PostgreSQL (production) backends
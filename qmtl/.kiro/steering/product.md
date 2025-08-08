# Product Overview

QMTL is a trading strategy orchestration system that executes strategies as directed acyclic graphs (DAGs). The system optimizes computational efficiency by deduplicating and reusing calculations across multiple strategies.

## Core Components

- **SDK**: Strategy development framework for building reusable nodes and DAGs
- **Gateway**: State management and DAG forwarding service with FSM-based execution control
- **DAG Manager**: Global DAG storage and queue orchestration using Neo4j and Kafka
- **Pipeline**: Local and distributed execution engine with Ray support

## Key Features

- **DAG-based Strategy Execution**: Strategies are composed as nodes in directed acyclic graphs
- **Computation Deduplication**: Identical nodes across strategies share results via message queues
- **Multi-mode Execution**: Supports backtest, dry-run, and live trading modes
- **Time-series Processing**: Built-in support for interval-based data processing with configurable periods
- **Tag-based Node Discovery**: Dynamic upstream selection using tag queries
- **Extensible Architecture**: Modular design with optional indicators, generators, transforms, and I/O modules

## Target Use Cases

- Quantitative trading strategy development and backtesting
- Real-time strategy execution with resource optimization
- Multi-strategy portfolio management
- Financial data processing and analysis pipelines
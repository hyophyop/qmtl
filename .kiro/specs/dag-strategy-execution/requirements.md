# Requirements Document

## Introduction

This document outlines the requirements for implementing a DAG-based strategy execution system for QMTL. The system enables efficient execution of trading strategies as directed acyclic graphs (DAGs) with computation deduplication and resource optimization. The core functionality includes DAG node identification, global DAG storage, queue orchestration, and multi-mode strategy execution with interval-based data processing.

## Requirements

### Requirement 1

**User Story:** As a strategy developer, I want to define trading strategies as DAG nodes with deterministic identifiers, so that identical computations can be reused across multiple strategies.

#### Acceptance Criteria

1. WHEN a strategy node is created THEN the system SHALL generate a deterministic NodeID based on (node_type, code_hash, config_hash, schema_hash)
2. WHEN two nodes have identical NodeID THEN the system SHALL reuse the computation result from the first node
3. WHEN a node is defined with interval and period parameters THEN the system SHALL validate these parameters are within acceptable ranges
4. IF a node lacks required interval parameter THEN the system SHALL reject the node definition with a clear error message

### Requirement 2

**User Story:** As a system operator, I want DAG differences to be computed and stored globally, so that computation resources are optimized across all running strategies.

#### Acceptance Criteria

1. WHEN a new DAG is submitted THEN the Gateway SHALL compare it against the global DAG in Neo4j
2. WHEN identical nodes are found in the global DAG THEN the system SHALL mark those nodes for queue reuse instead of recomputation
3. WHEN new nodes are identified THEN the DAG Manager SHALL create corresponding Kafka topics for data streaming
4. WHEN DAG diff operation completes THEN the system SHALL return a mapping of node execution requirements to the SDK

### Requirement 3

**User Story:** As a strategy developer, I want nodes to process time-series data with configurable intervals and periods, so that I can implement various technical analysis strategies.

#### Acceptance Criteria

1. WHEN a node receives upstream data THEN the system SHALL store it in a 4-D tensor structure C[u,i,p,f] where u=upstream_id, i=interval, p=period_slot, f=feature_index
2. WHEN a node's period requirement is satisfied (∀u ∈ upstreams : len(cache[u][interval]) ≥ period) THEN the system SHALL trigger the node's compute function
3. WHEN data exceeds the period window THEN the system SHALL evict old data using FIFO policy
4. IF upstream data is missing or delayed THEN the system SHALL apply the configured missing data policy (skip/fail)

### Requirement 4

**User Story:** As a strategy developer, I want to execute strategies in different modes (backtest, dry-run, live), so that I can validate strategies before deploying them in production.

#### Acceptance Criteria

1. WHEN backtest mode is selected THEN the system SHALL require explicit start_time and end_time parameters
2. WHEN dry-run mode is selected THEN the system SHALL replace trading execution nodes with paper trading equivalents
3. WHEN live mode is selected THEN the system SHALL execute actual trading operations through configured brokers
4. WHEN any execution mode is started THEN the system SHALL ensure all nodes meet their period requirements before processing

### Requirement 5

**User Story:** As a strategy developer, I want to use tag-based queries to automatically discover and connect to relevant upstream data sources, so that I don't need to hardcode specific queue names.

#### Acceptance Criteria

1. WHEN a TagQueryNode is defined with query_tags THEN the system SHALL find all matching queues in the global DAG
2. WHEN new queues matching the tags are added THEN the system SHALL automatically update the node's upstream connections
3. WHEN multiple queues match the tag query THEN the system SHALL aggregate the data according to the specified compute function
4. WHEN tag query returns no matches THEN the system SHALL log a warning and keep the node in waiting state

### Requirement 6

**User Story:** As a system administrator, I want the system to handle concurrent DAG submissions and queue creation safely, so that system integrity is maintained under load.

#### Acceptance Criteria

1. WHEN multiple strategies submit identical nodes simultaneously THEN the system SHALL use Kafka's idempotent API to prevent duplicate topic creation
2. WHEN Gateway loses Redis state THEN the system SHALL recover using PostgreSQL Write-Ahead Logging and AOF
3. WHEN Neo4j or Kafka experiences failures THEN the system SHALL follow documented recovery procedures
4. WHEN system components restart THEN the system SHALL restore state and resume processing without data loss

### Requirement 7

**User Story:** As a strategy developer, I want comprehensive monitoring and observability, so that I can troubleshoot issues and optimize performance.

#### Acceptance Criteria

1. WHEN strategies are executing THEN the system SHALL collect Prometheus metrics for diff_duration, nodecache_resident_bytes, and sentinel_gap_count
2. WHEN performance thresholds are exceeded THEN the system SHALL trigger alerts through configured channels
3. WHEN nodes are in pre-warmup state THEN the system SHALL log the status and display it in monitoring dashboards
4. WHEN system events occur THEN the system SHALL emit CloudEvents for integration with external monitoring systems
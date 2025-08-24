---
scope: strategies directory
last-reviewed: 2025-08-24
canonical-guidelines: ../CONTRIBUTING.md
---

# Strategy Guidelines

These guidelines apply to all files under the `strategies/` directory. General repository setup and testing rules are described in the root [AGENTS.md](../AGENTS.md).

## Setup

Follow the instructions in the root `AGENTS.md` to set up the environment and run tests. No strategy-specific setup is required.

## Development

- Implement node processors as pure functions under `nodes/` so they can be reused across DAGs.
- Define strategy DAGs in `dags/` using `qmtl.dag_manager` for orchestration.
- Connect nodes by wiring explicit output keys to input parameters; the graph must remain acyclic and each node name unique.
- Use `snake_case` for file and function names. Name node processor functions with the `_node` suffix and DAG modules with the `_dag.py` suffix.

## Testing

- Add tests for strategy behavior under `strategies/tests/`.
- Run the repository's test suite from the project root as documented in the root `AGENTS.md`.


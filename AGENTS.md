# Development Guidelines

This repository hosts strategy experiments built on top of the [QMTL](qmtl/README.md) submodule. Use this document to keep workflows consistent and to leverage QMTL effectively.

## Setup

- Initialize the submodule after cloning:
  ```bash
  git submodule update --init --recursive
  ```
- Manage dependencies with [uv](https://github.com/astral-sh/uv):
  ```bash
  uv pip install -e qmtl[dev]
  ```
  Install additional packages in the same environment when needed.

## Development Practices

- Follow the Single Responsibility Principle for every strategy, generator, indicator and transform.
- Add reusable components under `strategies/`, `generators/`, `indicators/` or `transforms/`. Place tests in `qmtl/tests/` or a local `tests/` directory.
- Manage node processors under `strategies/nodes/` and define strategy DAGs in `strategies/dags/`.
- Refer to `qmtl/architecture.md`, `qmtl/gateway.md` and `qmtl/dag-manager.md` for design details before modifying core behavior.
- See [strategies/README.md](strategies/README.md) for guidance on building and reusing node processors and DAGs.
- Use descriptive names and the `*_dsn` suffix for connection strings.
- When proposing task lists or improvements, highlight opportunities for parallel execution.
- Ensure resources such as network or database connections are closed to avoid `ResourceWarning`.

## Testing

- Run the full test suite and treat warnings as errors:
  ```bash
  uv run -m pytest -W error
  ```
- Commit only after tests pass without warnings.

## Running Strategies

- Update `strategy.py` to execute your strategy and verify with:
  ```bash
  python strategy.py
  ```


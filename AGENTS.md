# Development Guidelines

- Follow the Single Responsibility Principle (SRP) when designing modules and classes.
- All new features must include corresponding tests placed under the `tests/` directory.
- Manage the Python environment using **uv**. Install dependencies with
  `uv pip install -e .[dev]` and run tests in the uv environment. Build
  distributable wheels via `uv pip wheel .`.
- Use `pytest` for running tests. Ensure `pytest` succeeds before committing.
- Implementations must adhere to the specifications in `architecture.md`,
  `gateway.md` and `dag-manager.md`.

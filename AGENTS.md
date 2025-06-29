# Development Guidelines

- Follow the Single Responsibility Principle (SRP) when designing modules and classes.
- All new features must include corresponding tests placed under the `tests/` directory.
- Manage the Python environment using **uv**. Install dependencies with
  `uv pip install -e .[dev]` and run tests in the uv environment. Build
  distributable wheels via `uv pip wheel .`.
- Use `pytest` for running tests. Ensure `pytest` succeeds before committing.
- Implementations must adhere to the specifications in `architecture.md`,
  `gateway.md` and `dag-manager.md`.
- When providing task lists or suggestions, highlight opportunities for
  parallel execution where feasible.
- 질문에 대한 답이나 제안을 요청받은 경우에는 test 과정을 생략한다.

- All tests must pass without warnings.
- Run tests with `uv run -m pytest -W error` locally and in CI.
- Ensure proper resource cleanup (e.g., closing Redis connections) to avoid `ResourceWarning`.

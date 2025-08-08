# Development Guidelines

- Follow the Single Responsibility Principle (SRP) when designing modules and classes.
- All new features must include corresponding tests placed under the `tests/` directory.
- Manage the Python environment using **uv**. Install dependencies with
  `uv pip install -e .[dev]` and run tests in the uv environment. Build
  distributable wheels via `uv pip wheel .`.
- Implementations must adhere to the specifications in `architecture.md`,
  `gateway.md` and `dag-manager.md`.
- When providing task lists or suggestions, highlight opportunities for
  parallel execution where feasible.
- Pure review or suggestion tasks that do not modify code may skip running tests.
- For any code changes, run `uv run -m pytest -W error` locally and ensure the command completes without warnings. CI must also run this command without warnings.
- Ensure proper resource cleanup (e.g., closing Redis connections) to avoid `ResourceWarning`.

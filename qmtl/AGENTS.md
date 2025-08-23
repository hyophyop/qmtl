# Development Guidelines

- Follow the Single Responsibility Principle (SRP) when designing modules and classes.
- All new features must include corresponding tests placed under the `tests/` directory.
- Manage the Python environment using **uv**. Install dependencies with
  `uv pip install -e .[dev]` and run tests in the uv environment. Build
  distributable wheels via `uv pip wheel .`.
- Implementations must adhere to the specifications in `docs/architecture/architecture.md`,
  `docs/architecture/gateway.md` and `docs/architecture/dag-manager.md`.
- When providing task lists or suggestions, highlight opportunities for
  parallel execution where feasible.
- Pure review or suggestion tasks that do not modify code may skip running tests.
- For any code changes, run `uv run -m pytest -W error` locally and ensure the command completes without warnings. CI must also run this command without warnings.
- Ensure proper resource cleanup (e.g., closing Redis connections) to avoid `ResourceWarning`.
- Do not place alpha or strategy modules in `qmtl/`; only reusable feature extraction or data-processing utilities belong here. All alpha logic should live in the root project's `strategies/` directory.

# Documentation Management

- Store documentation in the `docs/` directory with descriptive filenames.
- Each Markdown file should start with a single `#` heading and use relative links to other docs.
- Update `mkdocs.yml` navigation when adding or moving files.
- Validate docs with `uv run mkdocs build` before committing. Ensure `mkdocs-macros-plugin` and `mkdocs-breadcrumbs-plugin` are installed via `uv pip install -e .[dev]`.

# Prioritizing external alpha ideas

- The top-level docs directory `docs/alphadocs/ideas/gpt5pro/` contains alpha ideas rewritten by a stronger model (GPT-5-Pro). These files should be treated as higher-priority implementation targets by agents and maintainers working within the `qmtl` project.
- When implementing from these documents inside `qmtl`, include `# Source: docs/alphadocs/ideas/gpt5pro/<doc>.md` and add `# Priority: gpt5pro` to the module header. Automated tooling should create an implementation branch/issue and record history in `docs/alphadocs_history.log`.

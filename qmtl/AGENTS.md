# Development Guidelines

**Applies to files under `qmtl/`.**

For general contribution and testing policies, see the repository root [AGENTS.md](../AGENTS.md).

## Environment

- Manage the Python environment using **uv**. Install dependencies with
  `uv pip install -e .[dev]` and build distributable wheels via `uv pip wheel .`.

## Architecture

- Implementations must adhere to the specifications in `docs/architecture/architecture.md`,
  `docs/architecture/gateway.md` and `docs/architecture/dag-manager.md`.
- Do not place alpha or strategy modules in `qmtl/`; only reusable feature extraction or
  data-processing utilities belong here. All alpha logic should live in the root project's
  `strategies/` directory.

## Documentation Management

- Store documentation in the `docs/` directory with descriptive filenames.
- Each Markdown file should start with a single `#` heading and use relative links to other docs.
- Update `mkdocs.yml` navigation when adding or moving files.
- Validate docs with `uv run mkdocs build` before committing. Ensure `mkdocs-macros-plugin`
  and `mkdocs-breadcrumbs-plugin` are installed via `uv pip install -e .[dev]`.

## Prioritizing external alpha ideas

- The top-level docs directory `docs/alphadocs/ideas/gpt5pro/` contains alpha ideas rewritten
  by a stronger model (GPT-5-Pro). These files should be treated as higher-priority
  implementation targets by agents and maintainers working within the `qmtl` project.
- When implementing from these documents inside `qmtl`, include
  `# Source: docs/alphadocs/ideas/gpt5pro/<doc>.md` and add `# Priority: gpt5pro` to the
  module header. Automated tooling should create an implementation branch/issue and record
  history in `docs/alphadocs_history.log`.

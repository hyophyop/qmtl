---
scope: qmtl subtree
last-reviewed: 2025-08-24
canonical-guidelines: ../CONTRIBUTING.md
---

# Development Guidelines

**Applies to files under `qmtl/`.**

For general contribution and testing policies, see the repository root [AGENTS.md](../AGENTS.md).

## Environment

- Manage the Python environment using **uv**. Install dependencies with
  `uv pip install -e .[dev]` and build distributable wheels via `uv pip wheel .`.

## Architecture

- Follow the upstream QMTL architecture docs (examples: architecture, gateway, DAG manager). In this subtree snapshot those files are not vendored; refer to the upstream repository documentation instead.
  - Upstream docs: https://github.com/hyophyop/qmtl
- Do not place alpha or strategy modules in `qmtl/`; only reusable feature extraction or
  data-processing utilities belong here. All alpha logic should live in the root project's
  `strategies/` directory.

## Documentation Management

- Store documentation in the `docs/` directory with descriptive filenames.
- Each Markdown file should start with a single `#` heading and use relative links to other docs.
- Update `mkdocs.yml` navigation when adding or moving files.
- Validate docs with `uv run mkdocs build` before committing. Ensure `mkdocs-macros-plugin`
  and `mkdocs-breadcrumbs-plugin` are installed via `uv pip install -e .[dev]`.

## Example Projects

Example strategies under `qmtl/examples/` follow the same conventions as the rest of the
project:

- Run tests with `uv run -m pytest -W error`.
- Place node processors under `nodes/` and tests under `tests/`.
- Keep functions pure and free of side effects.

## External alpha ideas

- Prioritization of alpha ideas (including `docs/alphadocs/ideas/gpt5pro/`) is managed at the repository root. The `qmtl/` subtree should not implement alphas directly; reference the root guidelines instead.

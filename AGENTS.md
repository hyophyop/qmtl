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

## Testing

- Always run tests in parallel with `pytest-xdist` for faster feedback:
  `uv run -m pytest -W error -n auto`
- If `pytest-xdist` is not installed, add it temporarily with
  `uv pip install pytest-xdist` (or add it to your local extras).
- For suites with shared resources, prefer `--dist loadscope` or cap workers
  (e.g., `-n 2`). Mark must‑be‑serial tests and run them separately.

## Example Projects

Example strategies under `qmtl/examples/` follow the same conventions as the rest of the
project:

- Run tests with `uv run -m pytest -W error -n auto`.
- Place node processors under `nodes/` and tests under `tests/`.
- Keep functions pure and free of side effects.

## Issue & PR Linking

- When work starts from a GitHub issue, include a closing keyword in both your final result message and the PR description so the issue auto‑closes on merge.
- Use one of: `Fixes #<number>`, `Closes #<number>`, or `Resolves #<number>` (e.g., `Fixes #123`).
- If referencing multiple issues, list each on its own line.
- For cross-repo issues, use `owner/repo#<number>` (e.g., `openai/qmtl#123`).
- If the change is partial and should not close the issue, prefer `Refs #<number>` instead of a closing keyword.
- Prefer placing the closing keyword in the PR body; commit messages on the default branch also work but are less visible.

Example PR snippet:

```
Summary: Implement data loader fallback path

Fixes #123
Also Refs #119 for broader tracking
```

## Prioritizing external alpha ideas

- The top-level docs directory `docs/alphadocs/ideas/gpt5pro/` contains alpha ideas rewritten
  by a stronger model (GPT-5-Pro). These files should be treated as higher-priority
  implementation targets by agents and maintainers working within the `qmtl` project.
- When implementing from these documents inside `qmtl`, include
  `# Source: docs/alphadocs/ideas/gpt5pro/<doc>.md` and add `# Priority: gpt5pro` to the
  module header. Automated tooling should create an implementation branch/issue and record
  history in `docs/alphadocs_history.log`.

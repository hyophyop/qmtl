## Contributing to qmtl-strategies

This repository contains strategy experiments that depend on the `qmtl/` subtree. Follow these guidelines to keep contributions consistent and reviewable. Repository-wide policies—such as the subtree workflow, testing, and AlphaDocs—are documented in [CONTRIBUTING.md](../CONTRIBUTING.md).

Key points
- Keep the `qmtl/` subtree in sync with the remote upstream before starting work. See [CONTRIBUTING.md](../CONTRIBUTING.md) for exact subtree commands.
- Run tests locally in the `uv` environment and ensure no warnings: `uv run -m pytest -W error`.
- When changing `qmtl/`, run and add tests under `qmtl/tests` and push subtree updates upstream as required by the policies in `CONTRIBUTING.md` and `qmtl/AGENTS.md`.

PR checklist (add to every PR description)
- [ ] Tests added or updated, and `uv run -m pytest -W error` passes locally
- [ ] If `qmtl/` was modified: included `git subtree push --prefix=qmtl qmtl-subtree main` step and confirm `git log -n 3 --oneline qmtl/` matches upstream
- [ ] Code follows style and naming conventions described in `strategies/AGENTS.md` (snake_case, `_node` suffix for node processors, `_dag.py` for DAG modules)
- [ ] AlphaDocs sync: if updating `docs/alphadocs/`, update `docs/alphadocs_registry.yml` and include `# Source: docs/alphadocs/<doc>.md` in relevant modules

Where to put project-level GitHub files
- `.github/` is the canonical place for templates and workflows. This repository provides example templates in this folder.

If you're unsure about the qmtl subtree workflow, read `CONTRIBUTING.md` and `qmtl/AGENTS.md` for detailed procedures.

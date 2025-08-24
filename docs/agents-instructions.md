# Agent / Developer Instructions

This file provides a quick reference for human and automated contributors. For full policies—including the QMTL subtree workflow, testing commands, and the AlphaDocs process—see [CONTRIBUTING.md](../CONTRIBUTING.md).

- Sync the `qmtl/` subtree before starting work and push upstream after changes.
- Run `uv run -m pytest -W error` and add tests near any new code.
- Research docs live in `docs/alphadocs/`; update `docs/alphadocs_registry.yml` and prioritize ideas under `docs/alphadocs/ideas/gpt5pro/`.

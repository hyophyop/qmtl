# Development Guidelines

This repository hosts strategy experiments built on top of the [QMTL](qmtl/README.md) subtree. For comprehensive policies—such as the QMTL subtree workflow, testing commands, and the AlphaDocs process—see [CONTRIBUTING.md](CONTRIBUTING.md).

Key reminders:

- Always synchronize the `qmtl/` subtree before starting work and push upstream after making changes.
- Strategy-specific code lives under `strategies/`; keep reusable utilities only in `qmtl/`.
- When modifying the subtree itself, follow `qmtl/AGENTS.md`. For strategy conventions, refer to `strategies/AGENTS.md`.

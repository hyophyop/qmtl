---
scope: repository root
last-reviewed: 2025-08-24
canonical-guidelines: CONTRIBUTING.md
---

# Development Guidelines

This repository hosts strategy experiments built on top of the [QMTL](qmtl/README.md) subtree. For comprehensive policies—such as the QMTL subtree workflow, testing commands, and the AlphaDocs process—see [CONTRIBUTING.md](CONTRIBUTING.md).

Key reminders:

- Always synchronize the `qmtl/` subtree before starting work and push upstream after making changes.
- Strategy-specific code lives under `strategies/`; keep reusable utilities only in `qmtl/`.
- When modifying the subtree itself, follow `qmtl/AGENTS.md`. For strategy conventions, refer to `strategies/AGENTS.md`.
- If any `AGENTS.md` files change, run `uv run python scripts/build_agent_instructions.py` to refresh `docs/agents-instructions.md` before committing. CI already runs this when relevant, so running it locally avoids surprises.

Terminology note: follow the repository’s terminology style guide in `CONTRIBUTING.md` (DAG, AlphaDocs vs `docs/alphadocs/`, Strategy vs strategy, etc.).

Automation helpers

- A pair of helper scripts are provided under `scripts/` to standardize common tasks:
	- `scripts/bootstrap.sh` — create `uv` venv, install editable `qmtl[dev]` deps and run a fast smoke test (strategies tests if present).
	- `scripts/sync_qmtl.sh` — fetch and pull the `qmtl` subtree from the `qmtl-subtree` remote and print recent commits for verification.

Please run `scripts/bootstrap.sh` when setting up a dev environment. Note: bootstrap performs a minimal setup and a quick smoke test; if you use pre-commit locally, also install and enable hooks with `uv run pre-commit install`. If you modify any files under `qmtl/`, run `scripts/sync_qmtl.sh` to pull upstream changes before making edits and follow subtree push instructions when pushing changes back upstream.

CI / Docs triggers

- The CI workflow will run the agent docs build step when `AGENTS.md` changes. If you update `AGENTS.md`, ensure `docs/agents-instructions.md` is refreshed by running (the builder scans the entire repo for `AGENTS.md` files):

```bash
uv run python scripts/build_agent_instructions.py
```

This repository's maintainers aim to keep the doc build step in CI to prevent stale agent instructions.

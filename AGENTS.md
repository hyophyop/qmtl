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
- When a task needs GitHub access (issues, PRs, metadata), use the `gh` CLI commands instead of manual web actions.

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
- Diagrams: Use Mermaid fenced code blocks (```mermaid) for all diagrams. Avoid PlantUML/DOT or binary diagram files; prefer text-based Mermaid for reviewability and versioning.

## Testing

- Always run tests in parallel with `pytest-xdist` for faster feedback:
  `uv run -m pytest -W error -n auto`
- If `pytest-xdist` is not installed, add it temporarily with
  `uv pip install pytest-xdist` (or add it to your local extras).
- For suites with shared resources, prefer `--dist loadscope` or cap workers
  (e.g., `-n 2`). Mark must‑be‑serial tests and run them separately.

### Test Design Strategy

Frame suites around three complementary lenses so coverage stays purposeful while the implementation remains free to evolve.

- **Contract Fidelity:** Anchor new and refactored suites in contract-style tests that lock observable guarantees—API signatures, CLI surfaces, return payloads, validation rules—without depending on internal helpers.
- **Collaboration Dynamics:** Exercise dispatch chains and service boundaries with consumer-driven expectations. Prefer spies/fakes to confirm orchestration (`dispatch -> run(create_project)`), required side effects, and cross-component message shapes.
- **Experience Guardrails:** Protect end-user flows with black-box behavioral checks and a slim smoke layer (command discovery, `--help`, happy-path scaffolds) to catch regressions quickly while keeping the suite fast.
- **Risk-Weighted Depth:** Lean into deeper scenario coverage for high-volatility or high-impact areas, mark serial or slow cases explicitly, and keep fixtures hermetic so tests compose cleanly under `-n auto`.

### Hang Detection Preflight (required in CI and recommended locally)

To prevent a single hanging test from blocking the entire suite, we run a fast
"preflight" that auto‑fails long runners before the full test job:

- Quick hang scan (no install step needed in CI/local):
  - `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`
  - Rationale: `pytest-timeout` turns hangs into failures with a traceback; `faulthandler` ensures a stack dump is emitted.
- Optional: collection sanity check to catch import‑time blocks early:
  - `uv run -m pytest --collect-only -q`
- After preflight passes, run the full suite:
  - `uv run -m pytest -W error -n auto`

Guidance for authors:
- If a test is expected to exceed 60s, add a per‑test timeout override: `@pytest.mark.timeout(180)`.
- Mark intentionally long or external‑dependency tests as `slow` and exclude them from preflight via `-k 'not slow'` if necessary.
- Prefer deterministic, dependency‑free tests; avoid unbounded network waits.

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

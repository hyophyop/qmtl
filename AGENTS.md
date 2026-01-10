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
- Before assuming external tools or services are unavailable, run a quick capability check for whichever CLI or API you plan to use (e.g., `gh auth status`, `aws sts get-caller-identity`, `docker info`). If the probe succeeds, leverage the tool immediately; if it fails, guide the user through re-auth or configuration and retry. Repeat this verification for each new session since tokens can expire or reset.

## Architecture

- Implementations must adhere to the specifications in `docs/ko/architecture/architecture.md`,
  `docs/ko/architecture/gateway.md` and `docs/ko/architecture/dag-manager.md` (canonical Korean docs;
  English translations live under `docs/en/architecture/`).
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
- When adding or modifying documentation utility scripts (e.g., `scripts/check_docs_links.py`),
  ensure that any new Python dependencies are reflected in both the developer installation
  instructions and the CI workflows (notably `.github/workflows/docs-link-check.yml`).
  Add an explicit installation step or shared requirements file in the workflow so the CI job
  installs packages such as `pyyaml` before running the script.

### Internationalization Policy

- Baseline language: Korean (`ko`). All other locales (including English) are translations of the Korean source documents.
- New or updated documentation should treat `docs/ko/...` as the canonical content; non‑Korean versions must not introduce normative content that does not exist in Korean.
- When introducing or updating documentation across 3 or more supported locales, ensure both Korean and English pages exist before completing the work. Other locales may follow subsequently, but `ko` and `en` must ship together in that change.
- Keep file paths mirrored by locale (e.g., `docs/ko/guides/foo.md` ↔ `docs/en/guides/foo.md`) and maintain the same heading structure and relative links.
- Validate builds for all affected locales with `uv run mkdocs build` and fix broken or missing links as part of the change. For broader i18n workflow details, see `docs/ko/guides/docs_internationalization.md`.

## Testing

- **PR gate (mandatory):** Do not open a PR until the full local CI gate passes (same commands and flags as CI; no “close enough” substitutions).
  - Run: `bash scripts/run_ci_local.sh`
  - Required outcome: exit code 0 with all steps green. If anything fails, fix locally first (or open a **draft** PR with explicit failing step + logs).
  - CI parity rules: use Python 3.11 (CI), run with `uv`, and do not change flags (e.g., don’t add `-n auto`, don’t drop `-W error`, don’t skip preflight).

- **Fast iteration (optional):** You may run narrower/parallelized commands while developing, but they do not replace the PR gate run.
  - Example: `uv run -m pytest -n auto -q tests/unit -q` (or the specific test module you touched).
  - If you need extra tooling (e.g., `pytest-xdist`), add it to the project’s dev dependencies (so CI and teammates match), rather than installing ad-hoc.

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
- After preflight passes, run the CI-equivalent suite command:
  - `PYTHONPATH=qmtl/proto uv run pytest -p no:unraisableexception -W error -q tests`
  - (Optional for iteration only) `PYTHONPATH=qmtl/proto uv run pytest -p no:unraisableexception -W error -n auto -q tests`

Guidance for authors:
- If a test is expected to exceed 60s, add a per‑test timeout override: `@pytest.mark.timeout(180)`.
- Mark intentionally long or external‑dependency tests as `slow` and exclude them from preflight via `-k 'not slow'` if necessary.
- Prefer deterministic, dependency‑free tests; avoid unbounded network waits.

## Complexity & Maintainability (radon)

Use radon metrics as a practical signal to guide refactors and keep the codebase healthy. Treat them as guardrails, not absolute rules—exceptions are allowed with a brief rationale and a follow‑up plan.

- Quick full scan (ad‑hoc):
  - `uv run --with radon -m radon cc -s -a qmtl`
  - `uv run --with radon -m radon mi -s qmtl`
  - `uv run --with radon -m radon raw -s qmtl`
- Diff‑only scan (what changed vs. main):
  - `git fetch origin`
  - CC (show C–F only): `git diff --name-only origin/main... | rg '\.py$' | xargs -r uv run --with radon -m radon cc -s -n C`
  - MI (show B–C only): `git diff --name-only origin/main... | rg '\.py$' | xargs -r uv run --with radon -m radon mi -s -n B`
- JSON for tooling/artifacts (optional):
  - `uv run --with radon -m radon cc -j -n C qmtl > .artifacts/radon_cc.json`
  - `uv run --with radon -m radon mi -j -n B qmtl > .artifacts/radon_mi.json`

Targets and actions:
- Cyclomatic Complexity (CC):
  - Target A/B per function/method; keep C rare and justified.
  - If you touch a C‑graded block, try to bring it to B or better.
  - D or worse should be refactored before merge unless a waiver is approved.
- Maintainability Index (MI):
  - Aim for A at the file level for changed files.
  - B is acceptable with rationale; C should not be introduced in new/changed files.
- Raw metrics (soft guardrails, not gates):
  - Keep functions small (≈ ≤ 50 LOC) and cohesive; split large modules (≈ ≥ 800 LOC).
  - Maintain docstrings for public APIs; keep comment density healthy (≈ 8–10%+).

Refactoring tips to lower CC / raise MI:
- Extract helpers to flatten deep nesting; use early returns/guard clauses.
- Replace long if/elif chains with a dispatch table or strategy objects.
- Separate error paths from the main happy path; avoid boolean flags controlling many branches.
- Prefer pure, composable functions; isolate I/O and side effects at the edges.

Exceptions and waivers (when metrics aren’t the right trade‑off):
- Acceptable reasons include: performance‑critical hot loops validated by profiling, parser/validation logic with inherently high branching, faithful adherence to external specs, or thin glue around third‑party APIs.
- Process:
  - Add a short comment near the block: `# complexity: waiver — reason (Refs #<issue>, YYYY‑MM‑DD)`.
  - Include a “Complexity waiver” section in the PR body listing file:function, metric/grade, reason, and the follow‑up plan.
  - Open a tracking issue labeled `tech-debt:complexity` if the waiver is not time‑boxed to the current PR.

Notes:
- Prefer diff‑based checks during development to avoid chasing legacy hotspots unrelated to your change (“leave the campsite cleaner than you found it”).
- Use `--exclude` or `--ignore` for generated files, examples, or tests when scans would be noisy (e.g., `-e "qmtl/examples/*,tests/*"`).

## Design & Coding Principles

- **SRP/SOC**: Separate input normalization/validation, core domain logic, and result/error mapping into distinct helpers/strategies. Keep handlers thin.
- **Strategy/Template**: If `if/elif` branches are 3+ for mode/option handling, replace them with a registry/strategy map or template method.
- **OCP/DRY**: Add new cases by registering a strategy/handler, not by editing existing control flow. Put shared parsing/validation/calculation/error mapping in helper modules—avoid local copy/paste.
- **Early return, flat flow**: Guard/exit early for invalid inputs and errors to avoid deep nesting.
- **Boundary purity**: Keep domain/calculation code pure or side‑effect minimal; wrap external I/O (HTTP/gRPC/SDK/files) behind adapters.
- **Error/option consistency**: Distinguish validation errors from business errors; keep option defaults/precedence in one helper; centralize error mapping per boundary (HTTP/gRPC/CLI).
- **Traceability (hot paths)**: For hot paths, maintain minimal structured logs/metrics outside core calculations.
- **Complexity guardrail**: If a C‑grade function is introduced or touched, either refactor to B+ or document the reason/plan in the PR and include `radon cc` results for changed files.

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

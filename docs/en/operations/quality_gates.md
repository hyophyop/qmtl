---
title: "Quality Gates"
tags:
  - operations
  - quality
  - ci
author: "QMTL Team"
last_modified: 2026-04-08
---

{{ nav_links() }}

# Quality Gates

This document defines how QMTL quality checks are split across PR hard gates, report-only signals, and pilot workflows. Korean (`docs/ko/...`) is the canonical source; English mirrors the same policy.

## Gate Classes

| Class | Tools/checks | Current enforcement | Purpose |
| --- | --- | --- | --- |
| PR hard gate | Ruff, deptry, radon diff, mypy, docs/link/i18n/import-cycle checks, packaging smoke, pytest/e2e suites | Blocks PRs on failure | Low-noise signals that should stop regressions immediately |
| Report-only signal | branch coverage baseline, Bandit, Vulture | No PR blocking; artifacts and summaries only | Baseline collection and noise classification |
| Pilot workflow | mutmut (`gateway/sdk/pipeline`) | Separate workflow, report-only | Measure survivor patterns and mutation-testing cost |

## Scan Scope Policy

| Tool | Default scan scope | Default exclusions | Policy rationale |
| --- | --- | --- | --- |
| Ruff | Whole repository | `notebooks/*.ipynb`, `qmtl/foundation/proto/*_pb2*.py` | Generated code and notebooks create too much repo-wide hard-gate noise |
| deptry | `qmtl/` | `qmtl/examples`, service tests, generated proto | Dependency hygiene is measured against the production package |
| coverage.py | `qmtl/` | `qmtl/examples`, generated proto | Tests are execution inputs, but the denominator stays on production code |
| Bandit | `qmtl/`, `scripts/`, `main.py`, `conftest.py` | `tests/`, `notebooks/`, `qmtl/examples/`, generated proto, `build/`, `dist/` | Security signals should include operational scripts as well as package code |
| Vulture | `qmtl/` | `tests/`, `notebooks/`, `qmtl/examples/`, generated proto, `build/`, `dist/` | Dead-code analysis becomes too noisy when scripts and tests are included |
| mutmut | `qmtl/runtime/sdk`, `qmtl/runtime/pipeline`, `qmtl/services/gateway` | generated proto | Restrict the pilot to high-change, high-value paths |

### Scope Rules

- `examples/` and `notebooks/` are treated as learning/demo assets and stay out of PR hard-gate denominators.
- Generated code (`qmtl/foundation/proto/*_pb2*.py`, `*_pb2_grpc.py`) is excluded from repo-wide static signals by default because it is not maintained manually.
- `tests/` remain execution input for coverage and mutation defense, but are not a default scan target for dead-code or security reports.
- Any new quality tool should document its scan scope and exclusions here before it is wired into CI.

## Execution Paths

### PR hard gate

- GitHub Actions: [`.github/workflows/ci.yml`]({{ code_url('.github/workflows/ci.yml') }})
- Local parity: [`scripts/run_ci_local.sh`]({{ code_url('scripts/run_ci_local.sh') }})

Both paths now perform the following in common:

- Ruff / deptry / radon diff / mypy
- docs strict build and link/design/i18n checks
- packaging smoke
- pytest preflight
- main test suite plus `world_smoke` and `core_loop`
- branch coverage baseline generation
- Bandit and Vulture report-only artifacts

### Mutation pilot

- Workflow: [`.github/workflows/mutation-pilot.yml`]({{ code_url('.github/workflows/mutation-pilot.yml') }})
- Local command: `bash scripts/run_mutation_pilot.sh`
- Optional selector example: `bash scripts/run_mutation_pilot.sh --selector 'qmtl.runtime.pipeline*'`
- Interpretation rule: the pilot is report-only, so a nonzero `exitcode.txt` does not block the PR hard gate. Instead, `summary.md` records the first failing test and an initial triage label.

## Artifact Locations

- coverage: `.artifacts/quality-gates/coverage/`
  - `coverage.json`, `coverage.xml`, `coverage.txt`
  - `summary.json`, `summary.md`
- Bandit: `.artifacts/quality-gates/security/bandit.json`
- Vulture: `.artifacts/quality-gates/deadcode/`
  - `vulture.txt`, `vulture.exitcode`
  - `summary.json`, `summary.md`
- mutmut pilot: `.artifacts/quality-gates/mutation/`
  - `mutmut.log`, `exitcode.txt`, `summary.md`, and `mutants.tgz` when available
  - `summary.md` also records the latest first failing test and whether the run currently looks like tooling noise.

## Staged Rollout Criteria

### Branch coverage

- Current stage: report-only baseline collection
- Next-stage candidates:
  1. Collect the overall `qmtl` branch-coverage baseline for at least two stable runs.
  2. Measure variance for the focus areas (`runtime/sdk`, `runtime/pipeline`, `services/gateway`).
  3. Introduce floors starting with the most stable focus areas.

### Bandit / Vulture

- Current stage: report-only
- Promotion criteria:
  - false-positive handling is documented,
  - repeated noise is removed without ad-hoc CLI suppressions,
  - baseline management can distinguish new findings from known noise.
- Triage rules:
  - `Bandit / needs fix`: findings in production paths around credential handling, shell injection, unsafe deserialization, or overly broad filesystem permissions are treated as fix-first issues. For example, any shell execution fed by user input should be patched rather than suppressed.
  - `Bandit / accepted risk`: only narrowly scoped subprocess or tempfile usage with clear intent may remain, and the rationale must live in centralized config plus triage notes. For example, a fixed internal command may be retained only with centralized justification.
  - `Bandit / tooling noise`: if test, example, or generated paths were scanned by mistake, fix the scan scope before adding any inline ignore.
  - `Vulture / candidate cleanup`: unreferenced helpers, imports, and locals are first-class cleanup candidates. If there is no runtime reachability evidence, remove them in the next cleanup patch.
  - `Vulture / keep but document`: externally invoked CLI entrypoints, compatibility shims, and reflection or dynamic-import hooks may stay if they are documented. A plugin hook loaded by string name is the typical example.
  - `Vulture / false positive`: framework entrypoints, plugin registries, and runtime-only dynamic symbols should repeat across runs before any suppression is added.
- Follow-up action by classification:
  - `Bandit / needs fix`, `Vulture / candidate cleanup`: patch or remove in the next code change set.
  - `Bandit / accepted risk`, `Vulture / keep but document`: keep only with centralized config and written rationale, then re-check on the next baseline refresh.
  - `Bandit / tooling noise`, `Vulture / false positive`: confirm recurrence before suppression, then adjust scan scope or baseline rules instead of hiding the signal inline.

### mutmut

- Current stage: separate pilot workflow
- Survivor buckets:
  - missing assertion
  - equivalent mutant
  - integration gap
  - flaky / tooling noise
- Survivor examples:
  - `missing assertion`: a return value or branch condition changes and the test still passes because the observable outcome was not asserted tightly enough. The follow-up action is to add a tighter assertion around that observable behavior.
  - `equivalent mutant`: the mutation changes syntax but not behavior under current domain constraints. The follow-up action is to tag it as `equivalent` and decide whether it should stay outside future gating denominators.
  - `integration gap`: unit coverage passes, but the cross-service contract or adapter boundary is not exercised, so the mutant survives. The follow-up action is to add contract or integration coverage at that boundary.
  - `flaky / tooling noise`: the current pilot example is the `tagquery_manager.stop()/poll_loop` cancellation path, where runner behavior can dominate the result. The follow-up action is to confirm reproducibility and either keep it tagged as tooling noise or move it into runner-stabilization work.
- Gate proposal criteria:
  - execution time and flake rate are stable,
  - equivalent-mutant volume is manageable,
  - at least one focus area has a reproducible baseline.

## Ignore / Waiver Policy

- Hard-gate exceptions must be centralized in config (`pyproject.toml`, `.bandit`) rather than hidden in ad-hoc CLI arguments.
- Report-only exceptions should first accumulate in artifacts and triage notes; only repeated noise should move into config.
- Mutation survivors should be tagged as `equivalent`, `not worth gating`, `needs test`, or `tooling noise`.

For baseline CI environment details, see [CI Environment](ci.md).

{{ nav_links() }}

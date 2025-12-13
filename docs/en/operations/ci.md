# CI Environment

Continuous Integration runs on Python 3.11 via uv-managed virtualenvs. Tests run with warnings treated as errors to catch resource leaks early.

- Python: 3.11 (managed by `uv python install 3.11` + `uv venv`)
- Dependency install: `uv pip install -e .[dev]`
- Protobuf generation: `uv run python -m grpc_tools.protoc ...`
- Tests: `PYTHONPATH=qmtl/proto uv run pytest -W error -n auto -q tests`

Parallelization uses `pytest-xdist`; ensure it is installed in the CI image.

See `.github/workflows/ci.yml` for the authoritative configuration.

## Hang Detection Preflight

Add a fast preflight stage before the full suite to ensure no test can hang the job. This uses `pytest-timeout` and `faulthandler` so any long‑running test fails with a traceback instead of blocking CI.

- Preflight command (no extra install step needed):

```
PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q \
  --timeout=60 --timeout-method=thread --maxfail=1
```

- Optional import/collection sanity check:

```
uv run -m pytest --collect-only -q
```

- Full suite after preflight:

```
PYTHONPATH=qmtl/proto uv run pytest -W error -n auto -q tests
```

### Example GitHub Actions snippet

Insert the following steps before the full test step:

```
      - name: Preflight – import/collection
        run: uv run -m pytest --collect-only -q

      - name: Preflight – hang detection
        run: |
          PYTHONFAULTHANDLER=1 \
          uv run --with pytest-timeout -m pytest -q \
            --timeout=60 --timeout-method=thread --maxfail=1

      - name: Run tests (warnings are errors)
        run: PYTHONPATH=qmtl/proto uv run pytest -p no:unraisableexception -W error -q tests
```

### Author guidance

- Tests that legitimately run >60s should set an explicit timeout:

```
@pytest.mark.timeout(180)
def test_long_running_case():
    ...
```

- Mark long/external tests as `slow` and, if needed, exclude them from preflight with `-k 'not slow'`.
- Avoid unbounded network waits; always set client timeouts in tests.

## Policy Diff Regression (CI/Cron)

- Goal: automatically monitor the impact ratio of policy changes against the “bad strategies” regression set.
- Example command:

```
uv run -m scripts.policy_diff_batch \
  --old docs/ko/world/sample_policy.yml \
  --new docs/ko/world/sample_policy.yml \
  --runs-dir operations/policy_diff/bad_strategies_runs \
  --runs-pattern '*.json' \
  --stage backtest \
  --output policy_diff_report.json \
  --fail-impact-ratio 0.05
```

- Artifact: upload `policy_diff_report.json`, and fail the workflow when the impact ratio exceeds the threshold.
- GitHub Actions workflow: `.github/workflows/policy-diff-regression.yml`
  - Runs automatically when `docs/**/world/sample_policy.yml` changes in a PR and uploads the report artifact
  - Also supports scheduled/manual triggers (default threshold `0.05`)

## Architecture Invariants (advisory checks)

Add lightweight checks (unit/integration) that fail fast when core invariants are violated:

- GSG NodeID uniqueness: no duplicate `node_id` across inserted nodes; NodeID computed via BLAKE3 canonicalization.
- World‑local isolation: applying a `DecisionsRequest` in World A must not affect World B state.
- EvalKey invalidation: changing `DatasetFingerprint`/`ContractID`/`CodeVersion` or `ResourcePolicy` produces a new `eval_key` and re‑validation.
- DecisionsRequest validation: empty or blank identifiers are rejected and duplicates are removed before persistence.

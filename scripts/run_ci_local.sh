#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run the repo's CI checks locally (CI-parity defaults).

Usage:
  bash scripts/run_ci_local.sh [--install] [--no-fetch] [--base <ref>]

Options:
  --install     Run 'uv pip install -e .[dev]' before checks.
  --no-fetch    Do not 'git fetch' before radon diff.
  --base <ref>  Base ref for radon diff (default: origin/main).
EOF
}

INSTALL=0
DO_FETCH=1
BASE_REF="origin/main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install) INSTALL=1; shift ;;
    --no-fetch) DO_FETCH=0; shift ;;
    --base) BASE_REF="${2:?missing --base value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

run_step() {
  local name="$1"
  shift
  echo
  echo "==> ${name}"
  "$@"
}

require_cmd uv
require_cmd git

export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.artifacts/uv-cache}"
export QUALITY_GATE_DIR="${QUALITY_GATE_DIR:-$PWD/.artifacts/quality-gates}"
mkdir -p "$UV_CACHE_DIR"
mkdir -p "$QUALITY_GATE_DIR"/{coverage,security,deadcode}

if [[ "$INSTALL" -eq 1 ]]; then
  run_step "Install dependencies (dev)" uv pip install -e ".[dev]"
fi

run_step "Ruff lint (repo-safe subset)" uv run --no-project --with ruff ruff check .

run_step "Dependency hygiene (deptry)" uv run --no-project --with deptry deptry qmtl

run_step "Docs link check" uv run python scripts/check_docs_links.py

run_step "Radon diff (CC/MI)" bash -lc '
  set -euo pipefail
  if [[ "'"$DO_FETCH"'" -eq 1 ]]; then
    git fetch origin main
  fi

  if command -v rg >/dev/null 2>&1; then
    changed=$(git diff --name-only "'"$BASE_REF"'..." | rg "\.py$" || true)
  else
    changed=$(git diff --name-only "'"$BASE_REF"'..." | grep -E "\.py$" || true)
  fi

  if [[ -z "$changed" ]]; then
    echo "No Python changes; skipping radon diff scan"
    exit 0
  fi

  cc_output=$(echo "$changed" | xargs uv run --with radon -m radon cc -s -n C)
  mi_output=$(echo "$changed" | xargs uv run --with radon -m radon mi -s -n C)
  echo "$cc_output"
  echo "$mi_output"
  if [[ -n "$cc_output" ]]; then
    echo "Radon CC found C-or-worse blocks in changed files"
    exit 1
  fi
  if [[ -n "$mi_output" ]]; then
    echo "Radon MI warnings (C-or-worse) in changed files:"
    echo "$mi_output"
  fi
'

run_step "Type check (mypy)" uv run --with mypy -m mypy
run_step "Build docs (mkdocs --strict)" uv run mkdocs build --strict
run_step "Check design drift (docs ↔ code)" uv run python scripts/check_design_drift.py
run_step "Check i18n core-loop parity (KO ↔ EN)" uv run python scripts/check_i18n_core_parity.py
run_step "Lint DSN keys (canonical *_dsn)" uv run python scripts/lint_dsn_keys.py
run_step "Check import cycles (grimp baseline)" uv run --with grimp python scripts/check_import_cycles.py --baseline scripts/import_cycles_baseline.json
run_step "Check SDK layer guard (core -> nodes)" uv run --with grimp python scripts/check_sdk_layers.py
run_step "Packaging smoke (wheel/sdist + CLI)" bash scripts/package_smoke.sh

run_step "Preflight – import/collection" uv run -m pytest --collect-only -q

run_step "Preflight – hang detection" bash -lc '
  set -euo pipefail
  PYTHONFAULTHANDLER=1 \
  uv run --with pytest-timeout -m pytest -q \
    --timeout=60 --timeout-method=thread --maxfail=1 -k "not slow"
'

run_step "Run tests with branch coverage (warnings are errors)" bash -lc '
  set -euo pipefail
  COVERAGE_FILE="'"$QUALITY_GATE_DIR"'/coverage/.coverage" \
  PYTHONPATH=qmtl/proto uv run --with pytest-cov -m pytest \
    -p no:unraisableexception -W error -q tests \
    --cov=qmtl --cov-branch --cov-report=
'

run_step "WorldService in-process smoke" bash -lc '
  set -euo pipefail
  USE_INPROC_WS_STACK=1 WS_MODE=service \
  COVERAGE_FILE="'"$QUALITY_GATE_DIR"'/coverage/.coverage" \
    uv run --with pytest-cov -m pytest -q tests/e2e/world_smoke -q \
      --cov=qmtl --cov-branch --cov-append --cov-report=
'

run_step "Core Loop contract suite" bash -lc '
  set -euo pipefail
  CORE_LOOP_STACK_MODE=inproc \
  COVERAGE_FILE="'"$QUALITY_GATE_DIR"'/coverage/.coverage" \
    uv run --with pytest-cov -m pytest -q tests/e2e/core_loop -q \
      --cov=qmtl --cov-branch --cov-append --cov-report=
'

run_step "Branch coverage baseline summary" bash -lc '
  set -euo pipefail
  COVERAGE_FILE="'"$QUALITY_GATE_DIR"'/coverage/.coverage" \
    uv run --with coverage python -m coverage json \
      -o "'"$QUALITY_GATE_DIR"'/coverage/coverage.json"
  COVERAGE_FILE="'"$QUALITY_GATE_DIR"'/coverage/.coverage" \
    uv run --with coverage python -m coverage xml \
      -o "'"$QUALITY_GATE_DIR"'/coverage/coverage.xml"
  COVERAGE_FILE="'"$QUALITY_GATE_DIR"'/coverage/.coverage" \
    uv run --with coverage python -m coverage report \
      > "'"$QUALITY_GATE_DIR"'/coverage/coverage.txt"
  uv run python scripts/summarize_coverage_baseline.py \
    --input "'"$QUALITY_GATE_DIR"'/coverage/coverage.json" \
    --json-output "'"$QUALITY_GATE_DIR"'/coverage/summary.json" \
    --markdown-output "'"$QUALITY_GATE_DIR"'/coverage/summary.md"
  cat "'"$QUALITY_GATE_DIR"'/coverage/summary.md"
'

run_step "Bandit report (report only)" bash -lc '
  set -euo pipefail
  uv run --no-project --with bandit bandit --ini .bandit \
    -r qmtl scripts main.py conftest.py \
    --severity-level medium --confidence-level medium \
    --format json -o "'"$QUALITY_GATE_DIR"'/security/bandit.json" \
    --exit-zero
  python - <<'"'"'PY'"'"'
import json
from collections import Counter
from pathlib import Path

report = Path("'"$QUALITY_GATE_DIR"'/security/bandit.json")
payload = json.loads(report.read_text(encoding="utf-8"))
results = payload.get("results", [])
counts = Counter(item["issue_severity"] for item in results)
print(f"Bandit findings: {len(results)}")
print("By severity:", dict(sorted(counts.items())))
PY
'

run_step "Vulture report (report only)" bash -lc '
  set -euo pipefail
  status=0
  uv run --no-project --with vulture vulture --config pyproject.toml \
    > "'"$QUALITY_GATE_DIR"'/deadcode/vulture.txt" || status=$?
  echo "$status" > "'"$QUALITY_GATE_DIR"'/deadcode/vulture.exitcode"
  uv run python scripts/summarize_vulture_report.py \
    --input "'"$QUALITY_GATE_DIR"'/deadcode/vulture.txt" \
    --json-output "'"$QUALITY_GATE_DIR"'/deadcode/summary.json" \
    --markdown-output "'"$QUALITY_GATE_DIR"'/deadcode/summary.md"
  cat "'"$QUALITY_GATE_DIR"'/deadcode/summary.md"
'

echo
echo "All local CI checks passed."

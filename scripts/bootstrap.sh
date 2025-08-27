#!/usr/bin/env bash
# Minimal bootstrap script to create a uv venv, install editable qmtl dev deps and run a smoke test
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

echo "Creating uv venv and installing development dependencies..."
pip install --upgrade pip || true
pip install uv || true
uv venv
uv pip install -e qmtl[dev]
uv pip install pyyaml || true

echo "Running a quick smoke test (strategy tests)..."
# Run only strategies tests for a fast smoke test if present
if [ -d "strategies/tests" ]; then
  uv run -m pytest strategies/tests -q --maxfail=1
else
  uv run -m pytest -q --maxfail=1
fi

echo "Bootstrap complete."

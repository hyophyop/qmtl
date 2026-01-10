#!/usr/bin/env bash
set -euo pipefail

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
require_cmd python

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
ARTIFACT_DIR="${ROOT_DIR}/.artifacts/package-smoke"
WHEEL_VENV="${ARTIFACT_DIR}/wheel-venv"
SDIST_VENV="${ARTIFACT_DIR}/sdist-venv"

rm -rf "$DIST_DIR" "$ARTIFACT_DIR"
mkdir -p "$DIST_DIR" "$ARTIFACT_DIR"

build_wheel() {
  if uv pip wheel . --no-deps -w "$DIST_DIR"; then
    return 0
  fi
  echo "uv pip wheel unavailable; falling back to uv build --wheel" >&2
  uv build --wheel --out-dir "$DIST_DIR"
}

rm -rf "${ROOT_DIR}/build"
run_step "Build sdist (python -m build)" uv run --with build python -m build --sdist --outdir "$DIST_DIR"
rm -rf "${ROOT_DIR}/build"
run_step "Build wheel (uv pip wheel)" build_wheel

wheel_file="$(ls -1 "$DIST_DIR"/*.whl | head -n 1)"
sdist_file="$(ls -1 "$DIST_DIR"/*.tar.gz | head -n 1)"

if [[ -z "$wheel_file" ]]; then
  echo "Wheel artifact not found in ${DIST_DIR}" >&2
  exit 1
fi

if [[ -z "$sdist_file" ]]; then
  echo "sdist artifact not found in ${DIST_DIR}" >&2
  exit 1
fi

run_step "Create wheel venv" uv venv "$WHEEL_VENV"
run_step "Install wheel" uv pip install --python "$WHEEL_VENV/bin/python" "$wheel_file"
run_step "Smoke CLI (wheel)" "$WHEEL_VENV/bin/qmtl" --help >/dev/null

run_step "Create sdist venv" uv venv "$SDIST_VENV"
run_step "Install sdist" uv pip install --python "$SDIST_VENV/bin/python" "$sdist_file"
run_step "Smoke CLI (sdist)" "$SDIST_VENV/bin/qmtl" --help >/dev/null

echo
echo "Packaging smoke checks passed."

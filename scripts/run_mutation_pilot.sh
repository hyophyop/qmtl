#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run the mutmut pilot for gateway/sdk/pipeline and store report-only artifacts.

Usage:
  bash scripts/run_mutation_pilot.sh [--selector <pattern>] [--output-dir <dir>]

Options:
  --selector <pattern>  Optional mutmut selector such as 'qmtl.runtime.pipeline*'.
  --output-dir <dir>    Artifact directory (default: .artifacts/quality-gates/mutation).
EOF
}

SELECTOR=""
OUTPUT_DIR=".artifacts/quality-gates/mutation"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --selector) SELECTOR="${2:?missing --selector value}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:?missing --output-dir value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/mutmut.log "$OUTPUT_DIR"/summary.md "$OUTPUT_DIR"/exitcode.txt
rm -rf mutants

status=0
if [[ -n "$SELECTOR" ]]; then
  uv run --no-project --with mutmut mutmut run "$SELECTOR" >"$OUTPUT_DIR/mutmut.log" 2>&1 || status=$?
else
  uv run --no-project --with mutmut mutmut run >"$OUTPUT_DIR/mutmut.log" 2>&1 || status=$?
fi

echo "$status" >"$OUTPUT_DIR/exitcode.txt"

if [[ -d mutants ]]; then
  tar -czf "$OUTPUT_DIR/mutants.tgz" mutants
fi

rm -rf mutants

failure_summary="$(
  python - "$OUTPUT_DIR/mutmut.log" <<'PY'
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""

failed_match = re.search(r"^FAILED\s+(.+)$", text, re.MULTILINE)
short_summary = ""
if failed_match:
    failed_test = failed_match.group(1).strip()
    reason = "unknown"
    if "CancelledError" in text:
        reason = "mutation-induced cancellation behavior under stop/poll loop"
    elif "RuntimeError: There is no current event loop" in text:
        reason = "tooling noise (missing event loop in pilot run)"
    print(f"- First failing test: `{failed_test}`")
    print(f"- Initial triage: `{reason}`")
PY
)"

{
  echo "# Mutation Pilot"
  echo
  echo "- Selector: \`${SELECTOR:-<configured scope>}\`"
  echo "- Exit code: \`$status\`"
  if [[ "$status" -eq 0 ]]; then
    echo "- Pilot status: \`clean report-only run\`"
  else
    echo "- Pilot status: \`non-blocking report-only failure captured\`"
  fi
  echo "- Configured scope comes from \`[tool.mutmut]\` in \`pyproject.toml\`."
  echo "- Artifacts: \`mutmut.log\` and, when available, \`mutants.tgz\`."
  if [[ -n "$failure_summary" ]]; then
    echo "$failure_summary"
  fi
  echo
  echo "Current mode: report-only pilot. Nonzero mutmut exits are recorded for triage and do not block the PR gate."
  echo "Survivors should be triaged into missing assertions, equivalent mutants, or workflow/noise buckets before any gate is proposed."
} >"$OUTPUT_DIR/summary.md"

exit 0

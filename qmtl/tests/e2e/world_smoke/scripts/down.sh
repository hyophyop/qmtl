#!/usr/bin/env bash
set -euo pipefail

for f in .gw.pid .dag.pid ; do
  if [[ -f "$f" ]]; then
    kill "$(cat "$f")" || true
    rm -f "$f"
  fi
done

echo "[down] done."


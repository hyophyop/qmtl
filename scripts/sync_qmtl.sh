#!/usr/bin/env bash
# Helper to fetch and pull qmtl subtree from upstream and show short verification steps.
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

if [ -z "${QMTL_SUBTREE_REMOTE:-}" ]; then
  QMTL_SUBTREE_REMOTE="qmtl-subtree"
fi

echo "Fetching from $QMTL_SUBTREE_REMOTE..."
git fetch "$QMTL_SUBTREE_REMOTE" main

echo "Pulling subtree into qmtl/ (squash)..."
git subtree pull --prefix=qmtl "$QMTL_SUBTREE_REMOTE" main --squash

echo "Recent commits in qmtl/:"
git log -n 5 --oneline qmtl/

echo "If there are conflicts, resolve them manually and re-run this script. To push changes back to upstream after modifying qmtl/, run:"
echo "  git subtree push --prefix=qmtl $QMTL_SUBTREE_REMOTE main"

echo "Done."

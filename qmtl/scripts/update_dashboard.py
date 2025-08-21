#!/usr/bin/env python3
"""Update document dashboard with last modified timestamps.

The script reads ``docs/dashboard.json`` and updates the ``last_updated`` field
for each document based on the file's modification time. A ``generated``
timestamp records when the dashboard was last refreshed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def update_dashboard(root: Path = ROOT, dashboard: Path | None = None) -> dict:
    """Update dashboard JSON file and return its data."""
    dashboard = dashboard or root / "docs" / "dashboard.json"

    if dashboard.exists():
        data = json.loads(dashboard.read_text())
    else:  # pragma: no cover - defensive path
        data = {"documents": []}

    for doc in data.get("documents", []):
        doc_path = root / doc["path"]
        if doc_path.exists():
            mtime = datetime.fromtimestamp(doc_path.stat().st_mtime, tz=timezone.utc)
            doc["last_updated"] = mtime.isoformat()
        else:
            doc["last_updated"] = None
            doc["status"] = "missing"

    data["generated"] = datetime.now(timezone.utc).isoformat()

    dashboard.write_text(json.dumps(data, indent=2) + "\n")
    return data


def main() -> int:
    update_dashboard()
    print("Dashboard updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

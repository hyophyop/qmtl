#!/usr/bin/env python3
"""List AlphaDocs entries grouped by status."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    import yaml
except Exception as exc:  # pragma: no cover - dependency error
    print(f"PyYAML required: {exc}")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "alphadocs_registry.yml"


def load_registry(registry: Path = REGISTRY) -> dict[str, list[str]]:
    """Return mapping of status to sorted list of docs."""
    data = yaml.safe_load(registry.read_text())
    status_map: dict[str, list[str]] = {}
    for entry in data or []:
        status = entry.get("status", "unknown")
        status_map.setdefault(status, []).append(entry["doc"])
    for docs in status_map.values():
        docs.sort()
    return dict(sorted(status_map.items()))


def format_table(status_map: dict[str, list[str]]) -> str:
    lines = ["STATUS\tDOC"]
    for status in sorted(status_map):
        for doc in status_map[status]:
            lines.append(f"{status}\t{doc}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json", "table"], default="table")
    args = parser.parse_args()

    status_map = load_registry()
    if args.format == "json":
        print(json.dumps(status_map, indent=2))
    else:
        print(format_table(status_map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

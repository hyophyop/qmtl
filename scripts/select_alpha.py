#!/usr/bin/env python3
"""Select alpha documents to implement, prioritizing GPT-5-Pro ideas."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
import sys

from list_alpha_status import REGISTRY, load_registry

try:
    import yaml
except Exception as exc:  # pragma: no cover - dependency error
    print(f"PyYAML required: {exc}")
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[1]


def load_entries(registry: Path = REGISTRY) -> list[dict]:
    """Return list of registry entries."""
    return yaml.safe_load(registry.read_text()) or []


def candidate_entries() -> list[dict]:
    """Return entries with status idea or draft, prioritized by source model."""
    status_map = load_registry()
    target_docs = set(status_map.get("idea", []) + status_map.get("draft", []))
    entries = [e for e in load_entries() if e.get("doc") in target_docs]
    entries.sort(key=lambda e: e.get("source_model") != "gpt5pro")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--random", type=int, nargs="?", const=1, help="Return N random candidates")
    group.add_argument("--top", type=int, nargs="?", const=1, help="Return top N candidates")
    parser.add_argument("--format", choices=["json", "table"], default="json")
    args = parser.parse_args()

    entries = candidate_entries()
    if not entries:
        print("No candidates found", file=sys.stderr)
        return 1

    if args.random is not None:
        k = min(args.random, len(entries))
        selected = random.sample(entries, k=k)
    else:
        k = args.top or 1
        selected = entries[:k]

    if args.format == "json":
        print(json.dumps(selected, indent=2))
    else:
        lines = ["DOC\tSTATUS\tSOURCE_MODEL"]
        for e in selected:
            lines.append(f"{e['doc']}\t{e.get('status','')}\t{e.get('source_model','')}")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

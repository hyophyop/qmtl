#!/usr/bin/env python3
"""Create a random idea file in docs/alphadocs/ideas/gpt5pro.

Behavior:
- Find all files under `docs/alphadocs/ideas` (recursively) excluding the `gpt5pro` subfolder.
- Find files under `docs/alphadocs/ideas/gpt5pro` (recursively).
- Choose a random file that exists in the former set but not the latter.
- Print the chosen file's relative path (from workspace root) and create an empty file at the corresponding path under `gpt5pro`.

Usage:
    python scripts/create_random_gpt5pro_idea.py

This script is idempotent: if there are no candidate files it will report and exit with code 1.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IDEAS_DIR = ROOT / "docs" / "alphadocs" / "ideas"
GPT5_DIR = IDEAS_DIR / "gpt5pro"


def gather_files(base: Path) -> set[Path]:
    """Return set of file paths relative to base for all regular files under base.

    Paths are returned as POSIX-style relative paths (Path objects) without the base prefix.
    """
    files = set()
    if not base.exists():
        return files
    for p in base.rglob("*"):
        if p.is_file():
            try:
                rel = p.relative_to(base)
            except Exception:
                rel = p
            files.add(rel)
    return files


def main() -> int:
    if not IDEAS_DIR.exists():
        print(f"Ideas directory not found: {IDEAS_DIR}")
        return 2

    all_files = gather_files(IDEAS_DIR)

    # Exclude any files under gpt5pro
    non_gpt5_files = {p for p in all_files if not str(p).split("/")[0] == "gpt5pro"}

    gpt5_files = gather_files(GPT5_DIR)

    # Candidates are those in non_gpt5_files not present in gpt5_files
    candidates = [p for p in non_gpt5_files if p not in gpt5_files]

    if not candidates:
        print("No candidate idea files found to add to gpt5pro.")
        return 1

    chosen = random.choice(candidates)

    # Destination path under gpt5pro
    dest = GPT5_DIR / chosen
    dest_parent = dest.parent
    dest_parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"Destination already exists: {dest.relative_to(ROOT)}")
        print(f"Chosen (but already present): docs/alphadocs/ideas/{chosen}")
        return 0

    # Create an empty file
    dest.write_text("")

    print(f"Created: {dest.relative_to(ROOT)}")
    print(f"Source idea: docs/alphadocs/ideas/{chosen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

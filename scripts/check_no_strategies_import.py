#!/usr/bin/env python3
"""Fail if the qmtl subtree imports the local strategies package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "qmtl"
    patterns = ["import strategies", "from strategies"]
    findings: list[str] = []
    for pattern in patterns:
        result = subprocess.run(
            ["rg", "--fixed-strings", "--glob", "*.py", pattern, str(root)],
            capture_output=True,
            text=True,
        )
        if result.stdout:
            findings.append(result.stdout)
    if findings:
        print("Found forbidden 'strategies' imports in qmtl subtree:")
        for out in findings:
            print(out)
        sys.exit(1)


if __name__ == "__main__":
    main()

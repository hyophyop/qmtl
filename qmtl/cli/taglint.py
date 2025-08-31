from __future__ import annotations

import argparse
from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``taglint`` subcommand."""

    parser = argparse.ArgumentParser(prog="qmtl taglint")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues")
    args, rest = parser.parse_known_args(argv)

    from qmtl.tools.taglint import main as taglint_main

    if args.fix:
        rest = ["--fix", *rest]
    taglint_main(rest)


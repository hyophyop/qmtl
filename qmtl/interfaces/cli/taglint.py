from __future__ import annotations

import argparse
from typing import List

from qmtl.utils.i18n import _


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``taglint`` subcommand."""

    argparse._ = _
    parser = argparse.ArgumentParser(prog="qmtl tools taglint", description=_("Lint TAGS dictionaries"))
    parser._ = _
    parser.add_argument("--fix", action="store_true", help=_("Attempt to fix issues"))
    args, rest = parser.parse_known_args(argv)

    from qmtl.interfaces.tools.taglint import main as taglint_main

    if args.fix:
        rest = ["--fix", *rest]
    taglint_main(rest)


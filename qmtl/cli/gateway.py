from __future__ import annotations

from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``gw`` subcommand."""

    from qmtl.gateway.cli import main as gw_main

    gw_main(argv)


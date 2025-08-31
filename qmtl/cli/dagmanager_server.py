from __future__ import annotations

from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for ``dagmanager-server`` subcommand."""

    from qmtl.dagmanager.server import main as server_main

    server_main(argv)


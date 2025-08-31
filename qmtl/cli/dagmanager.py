from __future__ import annotations

from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``dagmanager`` subcommand."""

    from qmtl.dagmanager.cli import main as dagm_main

    dagm_main(argv)


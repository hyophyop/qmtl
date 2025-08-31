from __future__ import annotations

from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for ``dagmanager-metrics`` subcommand."""

    from qmtl.dagmanager.metrics import main as metrics_main

    metrics_main(argv)


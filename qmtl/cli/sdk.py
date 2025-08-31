from __future__ import annotations

import logging
from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``sdk`` subcommand."""

    from qmtl.sdk.cli import main as sdk_main

    logging.basicConfig(level=logging.INFO)
    sdk_main(argv)


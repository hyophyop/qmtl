from __future__ import annotations

import logging
import sys
from typing import List


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``sdk`` subcommand."""

    from qmtl.runtime.sdk.cli import main as sdk_main

    logging.basicConfig(level=logging.INFO)
    sys.exit(sdk_main(argv))


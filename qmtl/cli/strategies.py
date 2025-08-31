from __future__ import annotations

import importlib
from typing import List


def run(argv: List[str] | None = None) -> None:  # noqa: ARG001 - argv unused
    """Entry point for the ``strategies`` subcommand."""

    strategy_main = importlib.import_module("strategies.strategy").main
    strategy_main()


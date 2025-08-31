from __future__ import annotations

import sys
from pathlib import Path
from typing import List


def run(argv: List[str] | None = None) -> None:  # noqa: ARG001 - argv unused
    """Entry point for the ``check-imports`` subcommand."""

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.check_no_strategies_import import main as check_imports_main

    raise SystemExit(check_imports_main())


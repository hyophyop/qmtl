from __future__ import annotations

import importlib
import logging
import sys
from typing import Callable, List, Optional


SdkMain = Callable[[Optional[List[str]]], Optional[int]]


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``sdk`` subcommand."""

    sdk_module = importlib.import_module("qmtl.runtime.sdk.cli")
    sdk_main = getattr(sdk_module, "main")
    sdk_main_callable: SdkMain = sdk_main

    logging.basicConfig(level=logging.INFO)
    sys.exit(sdk_main_callable(argv))


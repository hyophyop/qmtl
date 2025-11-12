"""Compatibility wrapper for the legacy ``add-layer`` command."""

from __future__ import annotations

from typing import List

from .layer import run_add


def run(argv: List[str] | None = None) -> None:
    run_add(argv)

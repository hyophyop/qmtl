"""Compatibility wrapper for the legacy ``validate`` command."""

from __future__ import annotations

from typing import List

from .layer import run_validate


def run(argv: List[str] | None = None) -> None:
    run_validate(argv)

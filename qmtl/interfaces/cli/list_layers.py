"""Compatibility wrapper for the legacy ``list-layers`` command."""

from __future__ import annotations

from typing import List

from .layer import run_list


def run(argv: List[str] | None = None) -> None:
    run_list(argv)

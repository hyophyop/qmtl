from __future__ import annotations

from typing import List


def run(argv: List[str] | None = None) -> None:  # noqa: ARG001 - unused
    """Entry point for the ``doc-sync`` subcommand."""

    from qmtl.scripts.check_doc_sync import main as doc_sync_main

    raise SystemExit(doc_sync_main())


"""Top level command line interface for qmtl.

QMTL v2.0 simplified CLI - single entry point for strategy submission.

Primary commands:
  submit   Submit a strategy for evaluation and activation
  status   Check status of submitted strategies
  world    World management commands
  init     Initialize a new project

Legacy commands (service, tools, project, config) have been removed.
"""

from __future__ import annotations

# Re-export v2 main as the primary entry point
from qmtl.interfaces.cli.v2 import main

# Legacy compatibility: PRIMARY_DISPATCH is no longer used in v2
# but some test helpers may still reference it
PRIMARY_DISPATCH: dict[str, str] = {}

__all__ = ["main", "PRIMARY_DISPATCH"]


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_backtest_defaults(ref_file: str | Path) -> dict[str, Any]:
    """Load backtest defaults from ``config.example.yml`` next to ``ref_file``.

    Parameters
    ----------
    ref_file:
        Path to a file whose sibling ``config.example.yml`` will be read.
    """
    path = Path(ref_file).with_name("config.example.yml")
    if path.exists():
        cfg = yaml.safe_load(path.read_text()) or {}
        return cfg.get("backtest", {})
    return {}


__all__ = ["load_backtest_defaults"]

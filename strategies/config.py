from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "backtest": {},
    "performance_metrics": {},
    "signal_thresholds": {},
    "risk_limits": {},
    "questdb_dsn": "postgresql://localhost:8812/qdb",
    "streams": [],
    "gateway_url": "http://localhost:8080",
    "dags": {},
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load strategy configuration from a YAML file.

    Parameters
    ----------
    path:
        Optional path to the configuration file. When omitted, the
        ``config.example.yml`` next to this module is used.
    """
    file_path = Path(path) if path else Path(__file__).with_name("config.example.yml")
    cfg = yaml.safe_load(file_path.read_text()) or {}
    return {key: cfg.get(key, value) for key, value in DEFAULT_CONFIG.items()}


__all__ = ["load_config"]

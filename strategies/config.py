from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


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
    return {
        "backtest": cfg.get("backtest", {}),
        "performance_metrics": cfg.get("performance_metrics", {}),
        "signal_thresholds": cfg.get("signal_thresholds", {}),
        "risk_limits": cfg.get("risk_limits", {}),
        "questdb_dsn": cfg.get("questdb_dsn", "postgresql://localhost:8812/qdb"),
        "streams": cfg.get("streams", []),
        "gateway_url": cfg.get("gateway_url", "http://localhost:8080"),
        "dags": cfg.get("dags", {}),
    }


__all__ = ["load_config"]

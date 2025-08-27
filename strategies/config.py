from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
    from dotenv import load_dotenv  # type: ignore
    has_dotenv = True
except ImportError:
    yaml = None  # type: ignore
    load_dotenv = None  # type: ignore
    has_dotenv = False


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
    """Load strategy configuration from a YAML file with environment variable support.

    Parameters
    ----------
    path:
        Optional path to the configuration file. When omitted, the
        ``qmtl.yml`` next to this module is used.
    """
    # Load environment variables from .env file if present
    if has_dotenv and load_dotenv:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

    # Determine config file path
    if path:
        file_path = Path(path)
    else:
        # Try qmtl.yml first, then fall back to config.example.yml
        qmtl_yml = Path(__file__).with_name("qmtl.yml")
        if qmtl_yml.exists():
            file_path = qmtl_yml
        else:
            file_path = Path(__file__).with_name("config.example.yml")

    # Load YAML configuration
    if yaml is None:
        raise ImportError("PyYAML is required but not installed")

    cfg: dict[str, Any] = yaml.safe_load(file_path.read_text()) or {}

    # Apply environment variable overrides
    cfg = apply_env_overrides(cfg)

    return {key: cfg.get(key, value) for key, value in DEFAULT_CONFIG.items()}


def apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to configuration."""
    # Database configuration
    if "DATABASE_BACKEND" in os.environ:
        config.setdefault("gateway", {})["database_backend"] = os.environ["DATABASE_BACKEND"]
    if "DATABASE_DSN" in os.environ:
        config.setdefault("gateway", {})["database_dsn"] = os.environ["DATABASE_DSN"]

    # Redis configuration
    if "REDIS_DSN" in os.environ:
        config.setdefault("gateway", {})["redis_dsn"] = os.environ["REDIS_DSN"]

    # Gateway configuration
    if "GATEWAY_HOST" in os.environ:
        config.setdefault("gateway", {})["host"] = os.environ["GATEWAY_HOST"]
    if "GATEWAY_PORT" in os.environ:
        config.setdefault("gateway", {})["port"] = int(os.environ["GATEWAY_PORT"])

    # DAG Manager configuration
    if "MEMORY_REPO_PATH" in os.environ:
        config.setdefault("dagmanager", {})["memory_repo_path"] = os.environ["MEMORY_REPO_PATH"]
    if "GRPC_HOST" in os.environ:
        config.setdefault("dagmanager", {})["grpc_host"] = os.environ["GRPC_HOST"]
    if "GRPC_PORT" in os.environ:
        config.setdefault("dagmanager", {})["grpc_port"] = int(os.environ["GRPC_PORT"])
    if "HTTP_HOST" in os.environ:
        config.setdefault("dagmanager", {})["http_host"] = os.environ["HTTP_HOST"]
    if "HTTP_PORT" in os.environ:
        config.setdefault("dagmanager", {})["http_port"] = int(os.environ["HTTP_PORT"])

    # Optional configurations
    if "NEO4J_DSN" in os.environ:
        config.setdefault("dagmanager", {})["neo4j_dsn"] = os.environ["NEO4J_DSN"]
    if "NEO4J_USER" in os.environ:
        config.setdefault("dagmanager", {})["neo4j_user"] = os.environ["NEO4J_USER"]
    if "NEO4J_PASSWORD" in os.environ:
        config.setdefault("dagmanager", {})["neo4j_password"] = os.environ["NEO4J_PASSWORD"]
    if "KAFKA_DSN" in os.environ:
        config.setdefault("dagmanager", {})["kafka_dsn"] = os.environ["KAFKA_DSN"]

    # Backtest configuration
    if "BACKTEST_START_TIME" in os.environ:
        config.setdefault("backtest", {})["start_time"] = os.environ["BACKTEST_START_TIME"]
    if "BACKTEST_END_TIME" in os.environ:
        config.setdefault("backtest", {})["end_time"] = os.environ["BACKTEST_END_TIME"]

    # Strategy configuration
    if "ENABLE_BINANCE_HISTORY" in os.environ:
        config.setdefault("dags", {})["binance_history"] = os.environ["ENABLE_BINANCE_HISTORY"].lower() == "true"
    if "ENABLE_ALPHA_SIGNAL" in os.environ:
        config.setdefault("dags", {})["alpha_signal"] = os.environ["ENABLE_ALPHA_SIGNAL"].lower() == "true"

    return config


__all__ = ["load_config"]

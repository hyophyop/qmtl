#!/usr/bin/env python3
"""Lint repository YAML configs for non-canonical connection-string keys.

Rules:
- For gateway/dagmanager sections, prefer *_dsn for redis/database/neo4j/kafka/controlbus.
- Transitional aliases like *_url/*_uri should not appear in committed configs.

Exit non-zero when violations are found. Intended for CI.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
import yaml


CANONICAL = {
    "gateway": {
        "redis_dsn",
        "database_dsn",
        "controlbus_dsn",
    },
    "dagmanager": {
        "neo4j_dsn",
        "kafka_dsn",
        "controlbus_dsn",
    },
}

ALIASES = {
    "gateway": {
        "redis_url": "redis_dsn",
        "redis_uri": "redis_dsn",
        "database_url": "database_dsn",
        "database_uri": "database_dsn",
        "controlbus_url": "controlbus_dsn",
        "controlbus_uri": "controlbus_dsn",
    },
    "dagmanager": {
        "neo4j_url": "neo4j_dsn",
        "neo4j_uri": "neo4j_dsn",
        "kafka_url": "kafka_dsn",
        "kafka_uri": "kafka_dsn",
        "controlbus_url": "controlbus_dsn",
        "controlbus_uri": "controlbus_dsn",
    },
}


def _iter_yaml_files(base: Path) -> list[Path]:
    files: list[Path] = []
    for p in base.rglob("*.yml"):
        if "/.venv/" in str(p):
            continue
        files.append(p)
    for p in base.rglob("*.yaml"):
        if "/.venv/" in str(p):
            continue
        files.append(p)
    return files


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text())
    except Exception:
        return None


def main() -> int:
    base = Path.cwd()
    offenders: list[str] = []
    for yf in _iter_yaml_files(base):
        data = _load_yaml(yf)
        if not isinstance(data, dict):
            continue
        for section in ("gateway", "dagmanager"):
            sec = data.get(section)
            if not isinstance(sec, dict):
                continue
            aliases = ALIASES[section]
            for bad_key, canonical in aliases.items():
                if bad_key in sec:
                    # Allow worldservice_url in gateway (not a DSN) and other unrelated keys
                    offenders.append(f"{yf}:{section}.{bad_key} -> use {canonical}")
    if offenders:
        sys.stderr.write("Non-canonical DSN keys found (use *_dsn):\n")
        for line in offenders:
            sys.stderr.write(f"  - {line}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


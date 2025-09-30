from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from qmtl.interfaces.cli import config


def _parse_assignment_value(raw: str) -> str:
    value = raw.split("=", 1)[1].strip()
    if value and value[0] in {'"', "'"}:
        return ast.literal_eval(value)
    return value


def _clear_qmtl_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("QMTL__") or key.startswith("QMTL_CONFIG_"):
            monkeypatch.delenv(key, raising=False)


def test_env_export_posix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_qmtl_env(monkeypatch)
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        """
gateway:
  host: 127.0.0.1
  redis_dsn: redis://localhost:6379/0
  controlbus_topics:
    - ingest
dagmanager:
  neo4j_password: hunter2
  kafka_dsn: kafka://broker:9092
        """.strip()
    )

    config.run(["env", "export", "--config", str(config_path)])
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]

    source_line = next(line for line in lines if line.startswith("export QMTL_CONFIG_SOURCE="))
    meta_line = next(line for line in lines if line.startswith("export QMTL_CONFIG_EXPORT="))

    source_value = _parse_assignment_value(source_line)
    meta_json = _parse_assignment_value(meta_line)
    metadata = json.loads(meta_json)

    assert Path(source_value) == config_path.resolve()
    assert metadata["include_secret"] is False
    assert metadata["secrets_omitted"] is True
    assert metadata["variables"] > 0

    # Secrets should be mentioned only in the comment, not exported.
    assignments = [line for line in lines if line.startswith("export ")]
    assert all(
        not line.startswith("export QMTL__DAGMANAGER__NEO4J_PASSWORD") for line in assignments
    )
    assert any("--include-secret" in line for line in lines if line.startswith("# "))
    assert any(line.startswith("export QMTL__GATEWAY__HOST") for line in assignments)


def test_env_show_masks(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _clear_qmtl_env(monkeypatch)
    monkeypatch.setenv("QMTL__GATEWAY__HOST", "0.0.0.0")
    monkeypatch.setenv("QMTL__DAGMANAGER__NEO4J_PASSWORD", "hunter2")

    config.run(["env", "show"])
    captured = capsys.readouterr()
    assert "QMTL__GATEWAY__HOST" in captured.out
    assert "0.0.0.0" in captured.out
    assert "hunter2" not in captured.out
    assert "********" in captured.out

    config.run(["env", "show", "--json"])
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    json_start = next(i for i, line in enumerate(lines) if line.startswith("["))
    payload = json.loads("\n".join(lines[json_start:]))

    password_entry = next(item for item in payload if item["key"].endswith("NEO4J_PASSWORD"))
    host_entry = next(item for item in payload if item["key"].endswith("GATEWAY__HOST"))

    assert password_entry["masked"] is True
    assert password_entry["value"] == "********"
    assert host_entry["masked"] is False
    assert host_entry["value"] == "0.0.0.0"


def test_env_clear_script(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _clear_qmtl_env(monkeypatch)
    monkeypatch.setenv("QMTL__GATEWAY__HOST", "0.0.0.0")
    monkeypatch.setenv("QMTL__DAGMANAGER__NEO4J_PASSWORD", "hunter2")

    config.run(["env", "clear"])
    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.strip().splitlines() if line.strip()]

    assert "unset QMTL__GATEWAY__HOST" in lines
    assert "unset QMTL__DAGMANAGER__NEO4J_PASSWORD" in lines
    assert "unset QMTL_CONFIG_SOURCE" in lines
    assert "unset QMTL_CONFIG_EXPORT" in lines

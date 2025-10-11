from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from qmtl.interfaces.cli import config as config_cli
from qmtl.foundation.config_validation import ValidationIssue


@pytest.fixture(autouse=True)
def reset_validators(monkeypatch):
    """Restore the original validators after each test."""

    original_gateway = config_cli.validate_gateway_config
    original_dagmanager = config_cli.validate_dagmanager_config
    yield
    monkeypatch.setattr(config_cli, "validate_gateway_config", original_gateway)
    monkeypatch.setattr(config_cli, "validate_dagmanager_config", original_dagmanager)


def _write_config(path: Path, data: Dict[str, Dict[str, object]]) -> None:
    path.write_text(json.dumps(data))


def test_validate_requires_requested_sections(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"gateway": {"host": "0.0.0.0"}})

    async def _fail_gateway(*_args, **_kwargs):  # pragma: no cover - sanity guard
        raise AssertionError("gateway validator should not run when section missing")

    async def _fail_dagmanager(*_args, **_kwargs):  # pragma: no cover - sanity guard
        raise AssertionError("dagmanager validator should not run when section missing")

    monkeypatch.setattr(config_cli, "validate_gateway_config", _fail_gateway)
    monkeypatch.setattr(config_cli, "validate_dagmanager_config", _fail_dagmanager)

    with pytest.raises(SystemExit) as exc:
        config_cli.run(["validate", "--config", str(config_path)])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "does not define the 'dagmanager' section" in captured.err


def test_validate_allows_target_subset(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"gateway": {"host": "127.0.0.1"}})

    async def _fake_gateway(_cfg, *, offline: bool = False):
        return {"redis": ValidationIssue("warning", "Redis DSN not configured")}

    monkeypatch.setattr(config_cli, "validate_gateway_config", _fake_gateway)

    config_cli.run(["validate", "--config", str(config_path), "--target", "gateway", "--json"])

    captured = capsys.readouterr()
    assert "gateway:" in captured.out
    lines = captured.out.splitlines()
    json_start = next(i for i, line in enumerate(lines) if line.startswith("{"))
    payload = json.loads("\n".join(lines[json_start:]))
    assert payload["status"] == "ok"
    assert "gateway" in payload["results"]
    assert payload["results"]["gateway"]["redis"]["severity"] == "warning"


def test_validate_runs_all_when_sections_present(tmp_path: Path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        {
            "gateway": {"host": "0.0.0.0"},
            "dagmanager": {"grpc_port": 5100},
        },
    )

    async def _fake_gateway(_cfg, *, offline: bool = False):
        return {"redis": ValidationIssue("ok", "Redis reachable")}

    async def _fake_dagmanager(_cfg, *, offline: bool = False):
        return {"neo4j": ValidationIssue("error", "Neo4j unavailable")}

    monkeypatch.setattr(config_cli, "validate_gateway_config", _fake_gateway)
    monkeypatch.setattr(config_cli, "validate_dagmanager_config", _fake_dagmanager)

    with pytest.raises(SystemExit) as exc:
        config_cli.run(["validate", "--config", str(config_path)])

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "gateway:" in captured.out
    assert "dagmanager:" in captured.out
    assert "Neo4j unavailable" in captured.out

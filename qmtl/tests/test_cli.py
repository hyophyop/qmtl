import os
import subprocess
import sys
import asyncio
from pathlib import Path

import pytest

from qmtl.sdk import cli as sdk_cli, runtime

STRATEGY_PATH = "tests.sample_strategy:SampleStrategy"


def test_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "sdk", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "usage: qmtl sdk" in result.stdout


def test_cli_dry_run():
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "sdk",
        STRATEGY_PATH,
        "--mode",
        "dryrun",
        "--gateway-url",
        "http://gw",
    ], capture_output=True, text=True)
    assert result.returncode != 0


def test_cli_offline():
    env = {**os.environ, "PYTHONPATH": str(Path(".."))}
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "sdk",
        STRATEGY_PATH,
        "--mode",
        "offline",
    ], capture_output=True, text=True, cwd="qmtl", env=env)
    assert result.returncode == 0
    assert "[OFFLINE] SampleStrategy" in result.stderr


@pytest.mark.asyncio
async def test_cli_sets_no_ray(monkeypatch):
    monkeypatch.setattr(runtime, "NO_RAY", False)
    await sdk_cli._main([
        STRATEGY_PATH,
        "--mode",
        "offline",
        "--no-ray",
    ])
    assert runtime.NO_RAY

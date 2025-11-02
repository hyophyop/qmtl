import os
import subprocess
import sys
import asyncio
from pathlib import Path

import pytest

from qmtl.foundation.config import TestConfig as FoundationTestConfig, UnifiedConfig
from qmtl.runtime.sdk.configuration import runtime_config_override
from qmtl.runtime.sdk import cli as sdk_cli, runtime

STRATEGY_PATH = "tests.sample_strategy:SampleStrategy"


def test_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "tools", "sdk", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "usage: qmtl tools sdk" in result.stdout


def test_cli_run_requires_args():
    # Missing required args should produce non-zero exit
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "tools",
        "sdk",
        "run",
        STRATEGY_PATH,
    ], capture_output=True, text=True)
    assert result.returncode != 0


def test_cli_offline():
    env = {**os.environ, "PYTHONPATH": str(Path(".."))}
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "tools",
        "sdk",
        "offline",
        STRATEGY_PATH,
    ], capture_output=True, text=True, cwd="qmtl", env=env)
    assert result.returncode == 0
    assert "[OFFLINE] SampleStrategy" in result.stderr


@pytest.mark.asyncio
async def test_cli_sets_no_ray(monkeypatch):
    monkeypatch.setattr(runtime, "NO_RAY", False)
    await sdk_cli._main([
        "offline",
        STRATEGY_PATH,
        "--no-ray",
    ])
    assert runtime.NO_RAY


@pytest.mark.asyncio
async def test_cli_run_uses_config_history(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_run_async(
        strategy_cls,
        *,
        world_id,
        gateway_url,
        history_start,
        history_end,
        **kwargs,
    ):
        captured.update(
            {
                "world_id": world_id,
                "gateway_url": gateway_url,
                "history_start": history_start,
                "history_end": history_end,
            }
        )

    monkeypatch.setattr(sdk_cli.Runner, "run_async", staticmethod(_fake_run_async))

    config = UnifiedConfig(test=FoundationTestConfig(history_start="7", history_end="19"))
    with runtime_config_override(config):
        await sdk_cli._main(
            [
                "run",
                STRATEGY_PATH,
                "--world-id",
                "world-123",
                "--gateway-url",
                "http://gateway",
            ]
        )

    assert captured["world_id"] == "world-123"
    assert captured["gateway_url"] == "http://gateway"
    assert captured["history_start"] == 7
    assert captured["history_end"] == 19


@pytest.mark.asyncio
async def test_cli_run_defaults_history_when_test_mode(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_run_async(
        strategy_cls,
        *,
        world_id,
        gateway_url,
        history_start,
        history_end,
        **kwargs,
    ):
        captured.update({"history_start": history_start, "history_end": history_end})

    monkeypatch.setattr(sdk_cli.Runner, "run_async", staticmethod(_fake_run_async))

    previous_test_mode = runtime.TEST_MODE
    runtime.TEST_MODE = True
    try:
        with runtime_config_override(UnifiedConfig()):
            await sdk_cli._main(
                [
                    "run",
                    STRATEGY_PATH,
                    "--world-id",
                    "world-test",
                    "--gateway-url",
                    "http://gateway",
                ]
            )
    finally:
        runtime.TEST_MODE = previous_test_mode

    assert captured["history_start"] == 1
    assert captured["history_end"] == 2

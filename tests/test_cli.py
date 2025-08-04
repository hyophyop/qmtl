import subprocess
import sys

STRATEGY_PATH = "tests.sample_strategy:SampleStrategy"


def test_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "sdk", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "usage: qmtl sdk" in result.stdout


def test_cli_dryrun():
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
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "sdk",
        STRATEGY_PATH,
        "--mode",
        "offline",
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert "[OFFLINE] SampleStrategy" in result.stderr

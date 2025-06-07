import subprocess
import sys
from pathlib import Path

STRATEGY_PATH = "tests.sample_strategy:SampleStrategy"


def test_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl.sdk", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Run QMTL strategy" in result.stdout


def test_cli_dryrun():
    result = subprocess.run([sys.executable, "-m", "qmtl.sdk", STRATEGY_PATH, "--mode", "dryrun"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "[DRYRUN] SampleStrategy" in result.stdout

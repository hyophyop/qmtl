import subprocess
import sys


def test_gateway_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "gw", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--config" in result.stdout


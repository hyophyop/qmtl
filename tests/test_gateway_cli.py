import subprocess
import sys


def test_gateway_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl.gateway", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--host" in result.stdout
    assert "--port" in result.stdout


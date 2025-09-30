import subprocess
import sys


def test_qmtl_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "gw" in result.stdout
    assert "dagmanager" in result.stdout
    assert "init" in result.stdout

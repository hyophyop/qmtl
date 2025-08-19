import subprocess
import sys

def test_cli_check_imports():
    result = subprocess.run([sys.executable, "-m", "qmtl", "check-imports"], capture_output=True, text=True)
    assert result.returncode == 0

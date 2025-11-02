import subprocess
import sys


def test_qmtl_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    for subcommand in ("config", "project", "service", "tools"):
        assert subcommand in result.stdout

    for deprecated in ("gw", "dagmanager", "init"):
        assert deprecated not in result.stdout

import subprocess
import sys
from pathlib import Path

from qmtl.scaffold import create_project


def test_create_project(tmp_path: Path):
    dest = tmp_path / "proj"
    create_project(dest)
    assert (dest / "qmtl.yml").is_file()
    assert (dest / "strategy.py").is_file()


def test_init_cli(tmp_path: Path):
    dest = tmp_path / "cli_proj"
    result = subprocess.run([
        sys.executable,
        "-m",
        "qmtl",
        "init",
        "--path",
        str(dest),
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert (dest / "qmtl.yml").is_file()
    assert (dest / "strategy.py").is_file()

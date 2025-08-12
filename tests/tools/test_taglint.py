import subprocess
import sys
from pathlib import Path


def run(path: Path, fix: bool = False):
    args = [sys.executable, "tools/taglint.py"]
    if fix:
        args.append("--fix")
    args.append(str(path))
    return subprocess.run(args, capture_output=True, text=True)


def test_taglint_valid(tmp_path):
    file = tmp_path / "ok.py"
    file.write_text(
        """TAGS = {\n    'scope': 'indicator',\n    'family': 'rsi',\n    'interval': '1m',\n    'asset': 'btc',\n}\n"""
    )
    res = run(file)
    assert res.returncode == 0, res.stdout + res.stderr


def test_taglint_missing(tmp_path):
    file = tmp_path / "missing.py"
    file.write_text("""def foo():\n    pass\n""")
    res = run(file)
    assert res.returncode != 0


def test_taglint_fix(tmp_path):
    file = tmp_path / "fix.py"
    file.write_text(
        """TAGS = {\n    'Scope': 'Indicator',\n    'family': 'rsi',\n    'interval': '60s',\n    'asset': 'BTC',\n}\n"""
    )
    res = run(file)
    assert res.returncode != 0
    res = run(file, fix=True)
    assert res.returncode == 0
    text = file.read_text()
    assert '"interval": "1m"' in text
    res = run(file)
    assert res.returncode == 0


def test_taglint_directory(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "ok.py").write_text(
        """TAGS = {\n    'scope': 'indicator',\n    'family': 'rsi',\n    'interval': '1m',\n    'asset': 'btc',\n}\n"""
    )
    res = run(pkg)
    assert res.returncode == 0

import subprocess
import sys
from pathlib import Path

from tests.qmtl.interfaces._cli_tokens import resolve_cli_tokens
from qmtl.interfaces.tools.taglint import (
    REQUIRED_KEYS,
    RECOMMENDED_KEYS,
    apply_fixes,
    load_tags,
    validate_tags,
)


TAGLINT_TOKENS = resolve_cli_tokens("qmtl.interfaces.cli.tools", "qmtl.interfaces.cli.taglint")


def run(path: Path, fix: bool = False):
    args = [sys.executable, "-m", "qmtl", *TAGLINT_TOKENS]
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


def test_taglint_valid_transform(tmp_path):
    file = tmp_path / "ok_transform.py"
    file.write_text(
        """TAGS = {\n    'scope': 'transform',\n    'family': 'scale',\n    'interval': '1m',\n    'asset': 'btc',\n}\n""",
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


def test_validate_tags_normalization():
    tags = {"Scope": "Indicator", "family": "rsi", "interval": "60s", "asset": "BTC"}
    fixed, errors = validate_tags(tags)
    assert fixed["scope"] == "indicator"
    assert fixed["interval"] == "1m"
    assert fixed["asset"] == "btc"
    assert any("keys and string values must be lowercase" in e for e in errors)
    assert any("not normalized" in e for e in errors)


def test_apply_fixes_adds_placeholders(tmp_path):
    file = tmp_path / "fix_tags.py"
    file.write_text("TAGS = {'scope': 'indicator'}\n")
    tags, node, tree = load_tags(str(file))
    fixed, errors = validate_tags(tags)
    assert errors  # missing keys reported
    apply_fixes(str(file), fixed, tree, node)
    new_tags, _, _ = load_tags(str(file))
    for key in REQUIRED_KEYS:
        assert key in new_tags
    for key in RECOMMENDED_KEYS:
        assert key not in new_tags

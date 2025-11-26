import os
import subprocess
import sys
from pathlib import Path


from qmtl.interfaces.tools.taglint import (
    REQUIRED_KEYS,
    RECOMMENDED_KEYS,
    apply_fixes,
    load_tags,
    validate_tags,
)


# v2 CLI: 'taglint' is an admin command, invoked via `qmtl --admin taglint`
TAGLINT_TOKENS = ["--admin", "taglint"]


def run(path: Path | None, *extra: str, fix: bool = False, env: dict[str, str] | None = None):
    args = [sys.executable, "-m", "qmtl", *TAGLINT_TOKENS]
    args.extend(extra)
    if fix:
        args.append("--fix")
    if path is not None:
        args.append(str(path))
    return subprocess.run(args, capture_output=True, text=True, env=env)


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


def test_taglint_help_respects_language_env():
    env = os.environ.copy()
    env["QMTL_LANG"] = "ko"
    res_en = run(None, "--help")
    res_ko = run(None, "--help", env=env)
    assert res_en.returncode == 0
    assert res_ko.returncode == 0
    assert "Attempt to fix issues" in res_en.stdout
    assert "Attempt to fix issues" not in res_ko.stdout
    assert "문제를 자동으로 수정합니다" not in res_en.stdout
    assert "문제를 자동으로 수정합니다" in res_ko.stdout


def test_taglint_errors_localized(tmp_path):
    file = tmp_path / "bad.py"
    file.write_text("TAGS = {}\n")
    env = os.environ.copy()
    env["QMTL_LANG"] = "ko"
    res_en = run(file)
    res_ko = run(file, env=env)
    assert res_en.returncode != 0
    assert res_ko.returncode != 0
    assert "missing required key: scope" in res_en.stderr
    assert "missing required key: scope" not in res_ko.stderr
    assert "필수 키 누락" in res_ko.stderr

from __future__ import annotations

from pathlib import Path
import importlib.util


def load_check() -> callable:
    base = Path(__file__).resolve()
    candidates = []
    for p in base.parents:
        candidates.append(p / "scripts" / "check_docs_links.py")
        candidates.append(p / "qmtl" / "scripts" / "check_docs_links.py")
    script = next((c for c in candidates if c.exists()), None)
    if script is None:
        raise FileNotFoundError("check_docs_links.py not found")
    spec = importlib.util.spec_from_file_location("check_docs_links", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.check_docs_links


def test_detects_broken_relative_link(tmp_path: Path) -> None:
    check = load_check()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("See [ref](reference/unknown.md)")
    errors = check(tmp_path, docs)
    assert any("Broken link" in e for e in errors)


def test_accepts_valid_relative_link(tmp_path: Path) -> None:
    check = load_check()
    docs = tmp_path / "docs"
    (docs / "reference").mkdir(parents=True)
    (docs / "reference" / "known.md").write_text("ok")
    (docs / "index.md").write_text("See [ref](reference/known.md)")
    errors = check(tmp_path, docs)
    assert errors == []


def test_flags_deprecated_tests_paths(tmp_path: Path) -> None:
    check = load_check()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("See `tests/runtime/sdk/test_x.py`. Also tests/sdk/y.md")
    errors = check(tmp_path, docs)
    assert any("Deprecated tests path" in e for e in errors)


def test_allows_new_tests_qmtl_paths(tmp_path: Path) -> None:
    check = load_check()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("See `tests/qmtl/runtime/sdk/test_ok.py`.")
    errors = check(tmp_path, docs)
    assert errors == []


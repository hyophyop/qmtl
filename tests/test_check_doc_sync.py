from __future__ import annotations

from pathlib import Path
import importlib.util


def load_check_doc_sync() -> callable:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_doc_sync.py"
    spec = importlib.util.spec_from_file_location("check_doc_sync", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.check_doc_sync


def test_idea_files_are_ignored(tmp_path: Path) -> None:
    check_doc_sync = load_check_doc_sync()
    root = tmp_path
    doc_dir = root / "docs" / "alphadocs"
    idea_file = doc_dir / "ideas" / "ignored_test.md"
    idea_file.parent.mkdir(parents=True)
    idea_file.write_text("test")
    registry = root / "docs" / "alphadocs_registry.yml"
    registry.write_text("[]\n")

    errors = check_doc_sync(root, registry, doc_dir)
    assert errors == []


def test_non_idea_files_trigger_error(tmp_path: Path) -> None:
    check_doc_sync = load_check_doc_sync()
    root = tmp_path
    doc_dir = root / "docs" / "alphadocs"
    doc_file = doc_dir / "unregistered_test.md"
    doc_file.parent.mkdir(parents=True)
    doc_file.write_text("test")
    registry = root / "docs" / "alphadocs_registry.yml"
    registry.write_text("[]\n")

    errors = check_doc_sync(root, registry, doc_dir)
    assert any("Docs not in registry" in e for e in errors)

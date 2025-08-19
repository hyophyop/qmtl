from pathlib import Path
import importlib.util


def load_check_doc_sync() -> callable:
    script_path = Path(__file__).resolve().parents[2] / "qmtl" / "scripts" / "check_doc_sync.py"
    spec = importlib.util.spec_from_file_location("check_doc_sync", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.check_doc_sync


def test_check_doc_sync(tmp_path: Path) -> None:
    check_doc_sync = load_check_doc_sync()

    root = tmp_path
    doc_dir = root / "docs" / "alphadocs"
    doc_dir.mkdir(parents=True)
    registry = root / "docs" / "alphadocs_registry.yml"
    registry.write_text(
        "- doc: docs/alphadocs/sample.md\n"
        "  status: implemented\n"
        "  modules:\n"
        "  - qmtl/qmtl/sample.py\n"
    )
    (doc_dir / "sample.md").write_text("# Sample\n")

    module_root = root / "qmtl" / "qmtl"
    module_root.mkdir(parents=True)
    (module_root / "sample.py").write_text("# Source: docs/alphadocs/sample.md\n")

    assert check_doc_sync(root, registry, doc_dir, module_root) == []

    registry.write_text(
        "- doc: docs/alphadocs/sample.md\n"
        "  status: implemented\n"
        "  modules: []\n"
    )
    errors = check_doc_sync(root, registry, doc_dir, module_root)
    assert any("annotation not registered" in e for e in errors)

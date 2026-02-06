from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    base = Path(__file__).resolve()
    candidates = []
    for parent in base.parents:
        candidates.append(parent / "scripts" / "check_design_drift.py")
        candidates.append(parent / "qmtl" / "scripts" / "check_design_drift.py")
    script = next((c for c in candidates if c.exists()), None)
    if script is None:
        raise FileNotFoundError("check_design_drift.py not found")

    spec = importlib.util.spec_from_file_location("check_design_drift", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_mkdocs_i18n(root: Path, *, default_locale: str = "ko") -> None:
    _write(
        root / "mkdocs.yml",
        f"""
plugins:
  - i18n:
      languages:
        - locale: {default_locale}
          default: true
        - locale: en
""".strip()
        + "\n",
    )


def _seed_spec(root: Path, mapping_literal: str) -> None:
    _write(
        root / "qmtl" / "foundation" / "spec.py",
        f"ARCH_SPEC_VERSIONS = {mapping_literal}\n",
    )


def _seed_arch_doc(root: Path, locale: str, stem: str, *, spec_version: str | None) -> None:
    header = ""
    if spec_version is not None:
        header = f"---\nspec_version: {spec_version}\n---\n\n"
    _write(
        root / "docs" / locale / "architecture" / f"{stem}.md",
        f"{header}# {stem}\n",
    )


def test_detects_missing_en_arch_doc_for_spec_key(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    (tmp_path / "docs" / "en" / "architecture").mkdir(parents=True, exist_ok=True)

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "[en] Missing architecture doc for spec key 'gateway'" in msg


def test_detects_version_mismatch_in_en_locale(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.1")

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "[en] Version mismatch" in msg


def test_warns_for_doc_declaring_unmapped_spec_version(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "ko", "extra", spec_version="v0.1")
    _seed_arch_doc(tmp_path, "en", "extra", spec_version="v0.1")

    code, msg = module.check_design_drift(tmp_path)

    assert code == 1
    assert "declares spec_version=v0.1 but no code mapping exists" in msg


def test_legacy_mode_skips_when_arch_docs_directory_missing(tmp_path: Path) -> None:
    module = load_module()
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")

    code, msg = module.check_design_drift(tmp_path)

    assert code == 0
    assert "No architecture docs; skipping design drift check" in msg

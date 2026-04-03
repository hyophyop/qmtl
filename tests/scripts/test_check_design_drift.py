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


def _seed_concept_doc(
    root: Path,
    locale: str,
    stem: str,
    concept_ids: list[str],
    *,
    section: str = "architecture",
) -> None:
    body = [f"# {stem}", ""]
    for concept_id in concept_ids:
        body.extend([f"## {concept_id}", "", f"Concept ID: `{concept_id}`", ""])
    _write(
        root / "docs" / locale / section / f"{stem}.md",
        "\n".join(body).rstrip() + "\n",
    )


def _seed_traceability_doc(
    root: Path,
    locale: str,
    yaml_body: str,
) -> None:
    _write(
        root / "docs" / locale / "architecture" / "implementation_traceability.md",
        "# implementation_traceability\n\n```yaml\n"
        + yaml_body.strip()
        + "\n```\n",
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


def test_parse_failure_with_localized_architecture_dirs_is_error(tmp_path: Path) -> None:
    module = load_module()
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _write(tmp_path / "mkdocs.yml", "plugins: [\n")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "Failed to parse mkdocs.yml i18n configuration" in msg


def test_nested_architecture_docs_are_reported(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")
    _write(
        tmp_path / "docs" / "ko" / "architecture" / "nested" / "future.md",
        "---\nspec_version: v1.0\n---\n\n# future\n",
    )
    _write(
        tmp_path / "docs" / "en" / "architecture" / "nested" / "future.md",
        "---\nspec_version: v1.0\n---\n\n# future\n",
    )

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "Nested architecture docs are not supported by design drift check" in msg


def test_traceability_passes_when_concepts_and_paths_are_mapped(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")
    _seed_concept_doc(tmp_path, "ko", "design_principles", ["PRIN-ONE"])
    _seed_concept_doc(tmp_path, "en", "design_principles", ["PRIN-ONE"])
    _seed_concept_doc(tmp_path, "ko", "capability_map", ["CAP-ONE"])
    _seed_concept_doc(tmp_path, "en", "capability_map", ["CAP-ONE"])
    _seed_concept_doc(tmp_path, "ko", "semantic_types", ["SEM-ONE"])
    _seed_concept_doc(tmp_path, "en", "semantic_types", ["SEM-ONE"])
    _seed_concept_doc(tmp_path, "ko", "decision_algebra", ["DEC-ONE"])
    _seed_concept_doc(tmp_path, "en", "decision_algebra", ["DEC-ONE"])
    _write(tmp_path / "qmtl" / "runtime" / "feature.py", "pass\n")
    _write(tmp_path / "tests" / "test_feature.py", "def test_ok():\n    assert True\n")
    yaml_body = """
traceability:
  - concept_id: PRIN-ONE
    source_doc: design_principles.md
    status: normative-only
  - concept_id: CAP-ONE
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/feature.py
    tests:
      - tests/test_feature.py
  - concept_id: SEM-ONE
    source_doc: semantic_types.md
    status: planned
  - concept_id: DEC-ONE
    source_doc: decision_algebra.md
    status: partial
    code:
      - qmtl/runtime/feature.py
"""
    _seed_traceability_doc(tmp_path, "ko", yaml_body)
    _seed_traceability_doc(tmp_path, "en", yaml_body)

    code, msg = module.check_design_drift(tmp_path)

    assert code == 0
    assert "Design drift check passed" in msg


def test_traceability_missing_doc_is_error_when_concepts_exist(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")
    seeded_ids = {
        "design_principles": ["DESIGN-PRINCIPLES-ONE"],
        "capability_map": ["CAPABILITY-MAP-ONE"],
        "semantic_types": ["SEMANTIC-TYPES-ONE"],
        "decision_algebra": ["DECISION-ALGEBRA-ONE"],
    }
    for stem, concept_ids in seeded_ids.items():
        _seed_concept_doc(tmp_path, "ko", stem, concept_ids)
        _seed_concept_doc(tmp_path, "en", stem, concept_ids)

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "Missing traceability doc" in msg


def test_traceability_missing_concept_mapping_is_error(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")
    _seed_concept_doc(tmp_path, "ko", "design_principles", ["PRIN-ONE"])
    _seed_concept_doc(tmp_path, "en", "design_principles", ["PRIN-ONE"])
    _seed_concept_doc(tmp_path, "ko", "capability_map", ["CAP-ONE"])
    _seed_concept_doc(tmp_path, "en", "capability_map", ["CAP-ONE"])
    _seed_concept_doc(tmp_path, "ko", "semantic_types", ["SEM-ONE"])
    _seed_concept_doc(tmp_path, "en", "semantic_types", ["SEM-ONE"])
    _seed_concept_doc(tmp_path, "ko", "decision_algebra", ["DEC-ONE"])
    _seed_concept_doc(tmp_path, "en", "decision_algebra", ["DEC-ONE"])
    yaml_body = """
traceability:
  - concept_id: PRIN-ONE
    source_doc: design_principles.md
    status: normative-only
"""
    _seed_traceability_doc(tmp_path, "ko", yaml_body)
    _seed_traceability_doc(tmp_path, "en", yaml_body)

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "Missing traceability entries for Concept IDs" in msg


def test_traceability_missing_code_path_is_error(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")
    _seed_concept_doc(tmp_path, "ko", "design_principles", ["PRIN-ONE"])
    _seed_concept_doc(tmp_path, "en", "design_principles", ["PRIN-ONE"])
    _seed_concept_doc(tmp_path, "ko", "capability_map", ["CAP-ONE"])
    _seed_concept_doc(tmp_path, "en", "capability_map", ["CAP-ONE"])
    _seed_concept_doc(tmp_path, "ko", "semantic_types", ["SEM-ONE"])
    _seed_concept_doc(tmp_path, "en", "semantic_types", ["SEM-ONE"])
    _seed_concept_doc(tmp_path, "ko", "decision_algebra", ["DEC-ONE"])
    _seed_concept_doc(tmp_path, "en", "decision_algebra", ["DEC-ONE"])
    yaml_body = """
traceability:
  - concept_id: PRIN-ONE
    source_doc: design_principles.md
    status: normative-only
  - concept_id: CAP-ONE
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/missing.py
    tests:
      - tests/test_feature.py
  - concept_id: SEM-ONE
    source_doc: semantic_types.md
    status: planned
  - concept_id: DEC-ONE
    source_doc: decision_algebra.md
    status: planned
"""
    _write(tmp_path / "tests" / "test_feature.py", "def test_ok():\n    assert True\n")
    _seed_traceability_doc(tmp_path, "ko", yaml_body)
    _seed_traceability_doc(tmp_path, "en", yaml_body)

    code, msg = module.check_design_drift(tmp_path)

    assert code == 2
    assert "references missing code path" in msg


def test_traceability_collects_contract_and_control_plane_concepts(tmp_path: Path) -> None:
    module = load_module()
    _seed_mkdocs_i18n(tmp_path)
    _seed_spec(tmp_path, "{'gateway': 'v1.2'}")
    _seed_arch_doc(tmp_path, "ko", "gateway", spec_version="v1.2")
    _seed_arch_doc(tmp_path, "en", "gateway", spec_version="v1.2")

    architecture_ids = {
        "design_principles": ["PRIN-ONE"],
        "capability_map": ["CAP-ONE"],
        "semantic_types": ["SEM-ONE"],
        "decision_algebra": ["DEC-ONE"],
        "core_loop_world_automation": ["CTRL-ONE"],
        "rebalancing_contract": ["CTRL-TWO"],
    }
    contract_ids = {
        "core_loop": ["CONTRACT-ONE"],
        "world_lifecycle": ["CONTRACT-TWO"],
    }

    for locale in ("ko", "en"):
        for stem, concept_ids in architecture_ids.items():
            _seed_concept_doc(tmp_path, locale, stem, concept_ids)
        for stem, concept_ids in contract_ids.items():
            _seed_concept_doc(
                tmp_path,
                locale,
                stem,
                concept_ids,
                section="contracts",
            )

    _write(tmp_path / "qmtl" / "runtime" / "feature.py", "pass\n")
    _write(tmp_path / "tests" / "test_feature.py", "def test_ok():\n    assert True\n")
    yaml_body = """
traceability:
  - concept_id: PRIN-ONE
    source_doc: design_principles.md
    status: normative-only
  - concept_id: CAP-ONE
    source_doc: capability_map.md
    status: implemented
    code:
      - qmtl/runtime/feature.py
    tests:
      - tests/test_feature.py
  - concept_id: SEM-ONE
    source_doc: semantic_types.md
    status: planned
  - concept_id: DEC-ONE
    source_doc: decision_algebra.md
    status: partial
    code:
      - qmtl/runtime/feature.py
  - concept_id: CONTRACT-ONE
    source_doc: core_loop.md
    status: partial
    code:
      - qmtl/runtime/feature.py
  - concept_id: CONTRACT-TWO
    source_doc: world_lifecycle.md
    status: partial
    code:
      - qmtl/runtime/feature.py
  - concept_id: CTRL-ONE
    source_doc: core_loop_world_automation.md
    status: partial
    code:
      - qmtl/runtime/feature.py
  - concept_id: CTRL-TWO
    source_doc: rebalancing_contract.md
    status: partial
    code:
      - qmtl/runtime/feature.py
"""
    _seed_traceability_doc(tmp_path, "ko", yaml_body)
    _seed_traceability_doc(tmp_path, "en", yaml_body)

    code, msg = module.check_design_drift(tmp_path)

    assert code == 0
    assert "Design drift check passed" in msg

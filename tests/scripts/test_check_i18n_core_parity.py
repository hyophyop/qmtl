from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    base = Path(__file__).resolve()
    candidates = []
    for parent in base.parents:
        candidates.append(parent / "scripts" / "check_i18n_core_parity.py")
        candidates.append(parent / "qmtl" / "scripts" / "check_i18n_core_parity.py")
    script = next((c for c in candidates if c.exists()), None)
    if script is None:
        raise FileNotFoundError("check_i18n_core_parity.py not found")

    spec = importlib.util.spec_from_file_location("check_i18n_core_parity", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_docs(root: Path, module, ko_text: str, en_text: str) -> None:
    for filename in module.CORE_LOOP_DOCS:
        _write(root / "docs" / "ko" / "architecture" / filename, ko_text)
        _write(root / "docs" / "en" / "architecture" / filename, en_text)


def test_reports_missing_mirrored_file(tmp_path: Path) -> None:
    module = load_module()
    base = "# Title\n\n## Section\n\n### Subsection\n\nMUST\n"
    _seed_docs(tmp_path, module, base, base)
    (tmp_path / "docs" / "en" / "architecture" / "controlbus.md").unlink()

    errors, warnings = module.check_i18n_core_parity(tmp_path)

    assert any("Missing mirrored file for controlbus.md" in err for err in errors)
    assert warnings == []


def test_reports_heading_level_sequence_mismatch(tmp_path: Path) -> None:
    module = load_module()
    ko = "# Title\n\n## Section\n\n### Subsection\n\nMUST\n"
    en = "# Title\n\n## Section\n\n### Subsection\n\nMUST\n"
    _seed_docs(tmp_path, module, ko, en)
    _write(
        tmp_path / "docs" / "en" / "architecture" / "gateway.md",
        "# Title\n\n## Section\n\n## Added\n\n## Added2\n\nMUST\n",
    )

    errors, warnings = module.check_i18n_core_parity(tmp_path)

    assert any(
        "Heading level sequence mismatch for gateway.md" in err for err in errors
    )
    assert warnings == []


def test_normative_marker_count_delta_is_warning_not_error(tmp_path: Path) -> None:
    module = load_module()
    ko = (
        "# Title\n\n## Section\n\n### Subsection\n\n"
        "MUST SHOULD SHALL\n\n"
        "```text\nMUST SHALL\n# heading-like\n```\n\n"
        "`SHALL`\n"
    )
    en = (
        "# Title\n\n## Section\n\n### Subsection\n\n"
        "MUST SHOULD SHALL MUST SHALL SHOULD MUST MUST SHALL SHOULD MUST SHALL\n"
    )
    _seed_docs(tmp_path, module, ko, en)

    errors, warnings = module.check_i18n_core_parity(tmp_path)

    assert errors == []
    assert any("Normative marker count differs noticeably" in warning for warning in warnings)


def test_normative_marker_presence_mismatch_fails(tmp_path: Path) -> None:
    module = load_module()
    stable = "# Title\n\n## Section\n\n### Subsection\n\nMUST SHALL SHOULD MUST SHALL\n"
    _seed_docs(tmp_path, module, stable, stable)
    _write(
        tmp_path / "docs" / "ko" / "architecture" / "worldservice.md",
        "# Title\n\n## Section\n\n### Subsection\n\n",
    )
    _write(
        tmp_path / "docs" / "en" / "architecture" / "worldservice.md",
        "# Title\n\n## Section\n\n### Subsection\n\nMUST SHALL SHOULD MUST SHALL SHOULD\n",
    )

    errors, warnings = module.check_i18n_core_parity(tmp_path)

    assert any(
        "Normative marker presence mismatch for worldservice.md" in err for err in errors
    )
    assert warnings == []


def test_main_returns_nonzero_with_actionable_output(
    tmp_path: Path, capsys
) -> None:
    module = load_module()

    rc = module.main(tmp_path)
    captured = capsys.readouterr().out

    assert rc == 1
    assert "i18n core-loop parity check failed:" in captured
    assert "Suggested fixes:" in captured

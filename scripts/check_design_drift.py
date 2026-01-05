#!/usr/bin/env python3
"""Design drift check: compare docs spec versions with code constants.

The documentation tree is locale-scoped (mkdocs i18n). This checker reads the
default locale from ``mkdocs.yml`` and validates the corresponding docs under
``docs/<default_locale>/architecture/*.md`` (falling back to the legacy
non-i18n path when present).

Exit codes:
- 0: OK or no docs declare ``spec_version``
- 1: Soft warning (no mapping in code for a doc with spec_version)
- 2: Mismatch or missing spec_version in docs for a known key

Set ``DRIFT_STRICT=1`` to treat all warnings as failures.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _default_locale(root: Path) -> str:
    mkdocs_path = root / "mkdocs.yml"
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(mkdocs_path.read_text(encoding="utf-8"))
        plugins = data.get("plugins", []) or []
        for ent in plugins:
            if not (isinstance(ent, dict) and "i18n" in ent):
                continue
            i18n_cfg = ent.get("i18n")
            if not isinstance(i18n_cfg, dict):
                break
            for lang in i18n_cfg.get("languages", []) or []:
                if isinstance(lang, dict) and lang.get("default") is True:
                    loc = lang.get("locale")
                    if loc:
                        return str(loc)
            break
    except Exception:
        # Default locale is Korean by policy; fall back defensively.
        return "ko"
    return "ko"


def _architecture_dir(root: Path) -> Path | None:
    default_locale = _default_locale(root)
    candidates = [
        root / "docs" / default_locale / "architecture",
        root / "docs" / "architecture",  # legacy, pre-i18n
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return None


def _read_front_matter(path: Path) -> dict[str, str]:
    """Parse a minimal YAML front-matter block into a dict.

    Only supports simple ``key: value`` pairs (strings). Stops at the second
    ``---``. Returns an empty dict when no front-matter is present.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        return {}
    lines = text.splitlines()[1:]
    out: dict[str, str] = {}
    for line in lines:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            out[key] = value
    return out


def check_design_drift(root: Path = ROOT) -> tuple[int, str]:
    # Late import to avoid import-time failures if qmtl isn't installed yet
    # Avoid importing the qmtl.foundation package to prevent import-time cycles.
    # Load the spec file directly.
    spec_file = root / "qmtl" / "foundation" / "spec.py"
    try:
        ns: dict[str, object] = {}
        code = spec_file.read_text(encoding="utf-8")
        exec(compile(code, str(spec_file), "exec"), ns, ns)
        ARCH_SPEC_VERSIONS = ns.get("ARCH_SPEC_VERSIONS", {})  # type: ignore[assignment]
        if not isinstance(ARCH_SPEC_VERSIONS, dict):
            raise RuntimeError("ARCH_SPEC_VERSIONS not found or invalid in spec.py")
    except Exception as exc:  # pragma: no cover - defensive
        return 2, f"Failed to load foundation spec: {exc}"

    arch_dir = _architecture_dir(root)
    if arch_dir is None:
        return 0, "No architecture docs; skipping design drift check"

    warnings: list[str] = []
    errors: list[str] = []

    for md in sorted(arch_dir.glob("*.md")):
        stem = md.stem  # e.g., 'gateway', 'dag-manager'
        fm = _read_front_matter(md)
        doc_ver = fm.get("spec_version")
        code_ver = ARCH_SPEC_VERSIONS.get(stem)

        if code_ver is None and doc_ver is not None:
            warnings.append(
                f"Doc {md} declares spec_version={doc_ver} but no code mapping exists (qmtl/foundation/spec.py)"
            )
            continue

        if code_ver is not None and doc_ver is None:
            errors.append(
                f"Doc {md} missing spec_version; expected {code_ver} in front-matter"
            )
            continue

        if code_ver is not None and doc_ver is not None and code_ver != doc_ver:
            errors.append(
                f"Version mismatch for {md}: docs={doc_ver} vs code={code_ver}"
            )

    strict = os.getenv("DRIFT_STRICT", "0") == "1"
    if errors:
        msg = [
            "Design drift check failed:",
            *errors,
            "",
            "Update qmtl/spec.py or the docs' spec_version to resolve.",
        ]
        return 2, "\n".join(msg)
    if warnings:
        msg = [
            "Design drift check warnings:",
            *warnings,
            "Set DRIFT_STRICT=1 to fail on warnings.",
        ]
        return (2 if strict else 1), "\n".join(msg)
    return 0, "Design drift check passed"


def main() -> int:
    code, msg = check_design_drift()
    print(msg)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

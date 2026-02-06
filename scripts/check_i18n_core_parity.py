#!/usr/bin/env python3
"""Guard KO<->EN parity for core-loop architecture docs.

Checks:
1) Mirrored file existence for required docs.
2) Top-level heading structure parity for H1/H2 (heading text is ignored).
3) Normative-marker presence parity (MUST/SHALL/SHOULD) for docs that contain
   substantial normative language.

Exit codes:
- 0: parity checks passed (warnings may be printed)
- 1: one or more parity violations found
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CORE_LOOP_DOCS: tuple[str, ...] = (
    "architecture.md",
    "gateway.md",
    "worldservice.md",
    "controlbus.md",
    "dag-manager.md",
    "ack_resync_rfc.md",
)
OPTIONAL_ARCH_DOCS: tuple[str, ...] = ("ack_resync_rfc.md",)

# Require explicit counterpart only when a document uses substantial normative
# markers. This avoids false positives in descriptive docs while still catching
# one-sided loss of normative constraints.
NORMATIVE_MIN_REQUIRED = 5

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_NORMATIVE_EN_RE = re.compile(r"\b(?:MUST|SHALL|SHOULD)\b")
_NORMATIVE_KO_RE = re.compile(
    r"(?:"
    r"반드시|"
    r"필수(?:이다|입니다|적이다|적입니다)?|"
    r"권고(?:한다|합니다|됨)?|"
    r"권장(?:한다|합니다|됨)?|"
    r"해야\s*한다|해야\s*합니다|"
    r"하여야\s*한다|하여야\s*합니다|"
    r"해서는\s*안\s*된다|"
    r"하면\s*안\s*된다|"
    r"금지(?:한다|합니다|됨)?"
    r")"
)


def _find_i18n_config(plugins: object) -> dict[str, object] | None:
    if not isinstance(plugins, list):
        return None
    for ent in plugins:
        if not (isinstance(ent, dict) and "i18n" in ent):
            continue
        cfg = ent.get("i18n")
        if isinstance(cfg, dict):
            return cfg
        return None
    return None


def _extract_default_locale(languages: object) -> str | None:
    if not isinstance(languages, list):
        return None
    for lang in languages:
        if not isinstance(lang, dict):
            continue
        if lang.get("default") is not True:
            continue
        locale = lang.get("locale")
        if locale:
            return str(locale)
    return None


def _load_i18n_default_locale(root: Path) -> str:
    """Return mkdocs i18n default locale, falling back to Korean policy default."""
    mkdocs_path = root / "mkdocs.yml"
    fallback = "ko"
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(mkdocs_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return fallback
    if not isinstance(data, dict):
        return fallback

    cfg = _find_i18n_config(data.get("plugins", []) or [])
    if cfg is None:
        return fallback
    return _extract_default_locale(cfg.get("languages", []) or []) or fallback


def _parity_locales(root: Path) -> tuple[str, str]:
    """Return (primary_locale, counterpart_locale) for parity checks."""
    default_locale = _load_i18n_default_locale(root)
    primary = default_locale
    counterpart = "en"
    if primary == counterpart:
        counterpart = "ko"
    return primary, counterpart


def _load_spec_doc_filenames(root: Path) -> tuple[str, ...]:
    """Return architecture doc filenames derived from ARCH_SPEC_VERSIONS."""
    spec_file = root / "qmtl" / "foundation" / "spec.py"
    try:
        ns: dict[str, object] = {}
        code = spec_file.read_text(encoding="utf-8")
        exec(compile(code, str(spec_file), "exec"), ns, ns)
        mapping = ns.get("ARCH_SPEC_VERSIONS", {})
        if not isinstance(mapping, dict):
            return ()
        return tuple(f"{str(key)}.md" for key in mapping.keys())
    except Exception:
        return ()


def _target_docs(root: Path, primary_arch: Path, counterpart_arch: Path) -> tuple[str, ...]:
    """Resolve parity target docs from spec map + known optional architecture docs."""
    docs = set(CORE_LOOP_DOCS)
    docs.update(_load_spec_doc_filenames(root))
    for filename in OPTIONAL_ARCH_DOCS:
        if (primary_arch / filename).exists() or (counterpart_arch / filename).exists():
            docs.add(filename)
    return tuple(sorted(docs))


def _iter_content_lines(path: Path) -> list[str]:
    """Return markdown lines excluding fenced code blocks."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[str] = []

    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in lines:
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            curr_char = fence[0]
            curr_len = len(fence)
            if not in_fence:
                in_fence = True
                fence_char = curr_char
                fence_len = curr_len
            elif curr_char == fence_char and curr_len >= fence_len:
                in_fence = False
                fence_char = ""
                fence_len = 0
            continue

        if not in_fence:
            out.append(line)

    return out


def _heading_levels(path: Path) -> list[int]:
    levels: list[int] = []
    for line in _iter_content_lines(path):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        if level <= 2:
            levels.append(level)
    return levels


def _normative_count(path: Path) -> int:
    count = 0
    for line in _iter_content_lines(path):
        # Inline code often contains examples rather than normative prose.
        cleaned = _INLINE_CODE_RE.sub("", line)
        count += len(_NORMATIVE_EN_RE.findall(cleaned))
        count += len(_NORMATIVE_KO_RE.findall(cleaned))
    return count


def _format_levels(levels: list[int], limit: int = 24) -> str:
    if not levels:
        return "<none>"
    compact = [f"H{lvl}" for lvl in levels]
    if len(compact) <= limit:
        return " ".join(compact)
    prefix = " ".join(compact[:limit])
    return f"{prefix} ... ({len(compact)} total)"


def _missing_mirror_error(
    filename: str,
    primary_file: Path,
    counterpart_file: Path,
    *,
    primary_locale: str,
    counterpart_locale: str,
) -> str | None:
    missing: list[str] = []
    if not primary_file.exists():
        missing.append(str(primary_file))
    if not counterpart_file.exists():
        missing.append(str(counterpart_file))
    if not missing:
        return None
    return (
        f"Missing mirrored file for {filename} ({primary_locale}<->{counterpart_locale}): "
        f"create missing counterpart(s): {', '.join(missing)}"
    )


def _heading_mismatch_error(
    filename: str,
    primary_file: Path,
    counterpart_file: Path,
    *,
    primary_locale: str,
    counterpart_locale: str,
) -> str | None:
    primary_levels = _heading_levels(primary_file)
    counterpart_levels = _heading_levels(counterpart_file)
    if primary_levels == counterpart_levels:
        return None

    mismatch_pos = next(
        (
            idx
            for idx, (primary_lvl, counterpart_lvl) in enumerate(
                zip(primary_levels, counterpart_levels), start=1
            )
            if primary_lvl != counterpart_lvl
        ),
        min(len(primary_levels), len(counterpart_levels)) + 1,
    )
    pos_desc = f"mismatch at heading #{mismatch_pos}" if mismatch_pos else "unknown mismatch"
    return (
        "Heading level sequence mismatch for "
        f"{filename} ({pos_desc}). "
        f"{primary_locale}={_format_levels(primary_levels)} | "
        f"{counterpart_locale}={_format_levels(counterpart_levels)} "
        "(H1/H2 sequence must match exactly)."
    )


def _normative_parity_messages(
    filename: str,
    primary_file: Path,
    counterpart_file: Path,
    *,
    primary_locale: str,
    counterpart_locale: str,
) -> tuple[str | None, str | None]:
    primary_normative = _normative_count(primary_file)
    counterpart_normative = _normative_count(counterpart_file)
    max_normative = max(primary_normative, counterpart_normative)
    min_normative = min(primary_normative, counterpart_normative)
    if max_normative >= NORMATIVE_MIN_REQUIRED and min_normative == 0:
        return (
            "Normative marker presence mismatch for "
            f"{filename}: {primary_locale}={primary_normative}, "
            f"{counterpart_locale}={counterpart_normative}. "
            "When one locale uses substantial normative markers, "
            "the mirrored locale must also include normative markers.",
            None,
        )
    if abs(primary_normative - counterpart_normative) > 6:
        return (
            None,
            "Normative marker count differs noticeably for "
            f"{filename}: {primary_locale}={primary_normative}, "
            f"{counterpart_locale}={counterpart_normative}. "
            "Review translation parity for normative language usage.",
        )
    return None, None


def check_i18n_core_parity(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for parity violations."""
    errors: list[str] = []
    warnings: list[str] = []
    docs_root = root / "docs"
    primary_locale, counterpart_locale = _parity_locales(root)
    primary_arch = docs_root / primary_locale / "architecture"
    counterpart_arch = docs_root / counterpart_locale / "architecture"
    target_docs = _target_docs(root, primary_arch, counterpart_arch)

    for filename in target_docs:
        primary_file = primary_arch / filename
        counterpart_file = counterpart_arch / filename

        missing_error = _missing_mirror_error(
            filename,
            primary_file,
            counterpart_file,
            primary_locale=primary_locale,
            counterpart_locale=counterpart_locale,
        )
        if missing_error:
            errors.append(missing_error)
            continue

        heading_error = _heading_mismatch_error(
            filename,
            primary_file,
            counterpart_file,
            primary_locale=primary_locale,
            counterpart_locale=counterpart_locale,
        )
        if heading_error:
            errors.append(heading_error)

        normative_error, normative_warning = _normative_parity_messages(
            filename,
            primary_file,
            counterpart_file,
            primary_locale=primary_locale,
            counterpart_locale=counterpart_locale,
        )
        if normative_error:
            errors.append(normative_error)
        elif normative_warning:
            warnings.append(normative_warning)

    return errors, warnings


def main(root: Path = ROOT) -> int:
    errors, warnings = check_i18n_core_parity(root)
    if errors:
        print("i18n core-loop parity check failed:")
        for error in errors:
            print(f"- {error}")
        print()
        print("Suggested fixes:")
        print("- Add missing mirrored files under the default locale architecture tree and docs/en/architecture.")
        print("- Keep H1/H2 heading structure in the same order across locales.")
        print("- Ensure normative markers exist in both locales for normative documents.")
        return 1

    if warnings:
        print("i18n core-loop parity warnings:")
        for warning in warnings:
            print(f"- {warning}")

    print("i18n core-loop parity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

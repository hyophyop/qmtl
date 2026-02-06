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

# Require explicit counterpart only when a document uses substantial normative
# markers. This avoids false positives in descriptive docs while still catching
# one-sided loss of normative constraints.
NORMATIVE_MIN_REQUIRED = 5

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_NORMATIVE_RE = re.compile(r"\b(?:MUST|SHALL|SHOULD)\b")


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
        count += len(_NORMATIVE_RE.findall(cleaned))
    return count


def _format_levels(levels: list[int], limit: int = 24) -> str:
    if not levels:
        return "<none>"
    compact = [f"H{lvl}" for lvl in levels]
    if len(compact) <= limit:
        return " ".join(compact)
    prefix = " ".join(compact[:limit])
    return f"{prefix} ... ({len(compact)} total)"


def _missing_mirror_error(filename: str, ko_file: Path, en_file: Path) -> str | None:
    missing: list[str] = []
    if not ko_file.exists():
        missing.append(str(ko_file))
    if not en_file.exists():
        missing.append(str(en_file))
    if not missing:
        return None
    return (
        f"Missing mirrored file for {filename}: "
        f"create missing counterpart(s): {', '.join(missing)}"
    )


def _heading_mismatch_error(filename: str, ko_file: Path, en_file: Path) -> str | None:
    ko_levels = _heading_levels(ko_file)
    en_levels = _heading_levels(en_file)
    min_len = min(len(ko_levels), len(en_levels))
    prefix_matches = ko_levels[:min_len] == en_levels[:min_len]
    length_delta = abs(len(ko_levels) - len(en_levels))
    if prefix_matches and length_delta <= 1:
        return None

    mismatch_pos = next(
        (
            idx
            for idx, (ko_lvl, en_lvl) in enumerate(zip(ko_levels, en_levels), start=1)
            if ko_lvl != en_lvl
        ),
        min_len + 1 if len(ko_levels) != len(en_levels) else None,
    )
    pos_desc = f"mismatch at heading #{mismatch_pos}" if mismatch_pos else "unknown mismatch"
    return (
        "Heading level sequence mismatch for "
        f"{filename} ({pos_desc}). "
        f"ko={_format_levels(ko_levels)} | en={_format_levels(en_levels)} "
        "(H1/H2 sequence must match; max length delta=1)."
    )


def _normative_parity_messages(
    filename: str, ko_file: Path, en_file: Path
) -> tuple[str | None, str | None]:
    ko_normative = _normative_count(ko_file)
    en_normative = _normative_count(en_file)
    max_normative = max(ko_normative, en_normative)
    min_normative = min(ko_normative, en_normative)
    if max_normative >= NORMATIVE_MIN_REQUIRED and min_normative == 0:
        return (
            "Normative marker presence mismatch for "
            f"{filename}: ko={ko_normative}, en={en_normative}. "
            "When one locale uses substantial MUST/SHALL/SHOULD markers, "
            "the mirrored locale must also include normative markers.",
            None,
        )
    if abs(ko_normative - en_normative) > 6:
        return (
            None,
            "Normative marker count differs noticeably for "
            f"{filename}: ko={ko_normative}, en={en_normative}. "
            "Review translation parity for MUST/SHALL/SHOULD usage.",
        )
    return None, None


def check_i18n_core_parity(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for parity violations."""
    errors: list[str] = []
    warnings: list[str] = []
    docs_root = root / "docs"
    ko_arch = docs_root / "ko" / "architecture"
    en_arch = docs_root / "en" / "architecture"

    for filename in CORE_LOOP_DOCS:
        ko_file = ko_arch / filename
        en_file = en_arch / filename

        missing_error = _missing_mirror_error(filename, ko_file, en_file)
        if missing_error:
            errors.append(missing_error)
            continue

        heading_error = _heading_mismatch_error(filename, ko_file, en_file)
        if heading_error:
            errors.append(heading_error)

        normative_error, normative_warning = _normative_parity_messages(filename, ko_file, en_file)
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
        print("- Add missing mirrored files under docs/ko/architecture and docs/en/architecture.")
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

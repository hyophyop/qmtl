#!/usr/bin/env python3
"""Guard KO<->EN parity for core-loop architecture docs.

Checks:
1) Mirrored file existence for required docs.
2) Heading level sequence parity for H1/H2/H3 (heading text is ignored).
3) Normative marker parity for MUST/SHALL/SHOULD counts with tolerance <= 2.

Exit codes:
- 0: parity checks passed
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

NORMATIVE_TOKEN_TOLERANCE = 2

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
        if level <= 3:
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


def check_i18n_core_parity(root: Path = ROOT) -> list[str]:
    """Return parity violations as actionable error strings."""
    errors: list[str] = []
    docs_root = root / "docs"
    ko_arch = docs_root / "ko" / "architecture"
    en_arch = docs_root / "en" / "architecture"

    for filename in CORE_LOOP_DOCS:
        ko_file = ko_arch / filename
        en_file = en_arch / filename

        if not ko_file.exists() or not en_file.exists():
            missing = []
            if not ko_file.exists():
                missing.append(str(ko_file))
            if not en_file.exists():
                missing.append(str(en_file))
            errors.append(
                f"Missing mirrored file for {filename}: create missing counterpart(s): {', '.join(missing)}"
            )
            continue

        ko_levels = _heading_levels(ko_file)
        en_levels = _heading_levels(en_file)
        if ko_levels != en_levels:
            mismatch_pos = next(
                (
                    idx
                    for idx, (ko_lvl, en_lvl) in enumerate(
                        zip(ko_levels, en_levels), start=1
                    )
                    if ko_lvl != en_lvl
                ),
                None,
            )
            pos_desc = (
                f"first mismatch at heading #{mismatch_pos}"
                if mismatch_pos is not None
                else "different number of H1/H2/H3 headings"
            )
            errors.append(
                "Heading level sequence mismatch for "
                f"{filename} ({pos_desc}). "
                f"ko={_format_levels(ko_levels)} | en={_format_levels(en_levels)}"
            )

        ko_normative = _normative_count(ko_file)
        en_normative = _normative_count(en_file)
        delta = abs(ko_normative - en_normative)
        if delta > NORMATIVE_TOKEN_TOLERANCE:
            errors.append(
                "Normative marker count mismatch for "
                f"{filename}: ko={ko_normative}, en={en_normative}, "
                f"delta={delta} (allowed <= {NORMATIVE_TOKEN_TOLERANCE}). "
                "Align MUST/SHALL/SHOULD markers across locales."
            )

    return errors


def main(root: Path = ROOT) -> int:
    errors = check_i18n_core_parity(root)
    if errors:
        print("i18n core-loop parity check failed:")
        for error in errors:
            print(f"- {error}")
        print()
        print("Suggested fixes:")
        print("- Add missing mirrored files under docs/ko/architecture and docs/en/architecture.")
        print("- Keep H1/H2/H3 heading structure in the same order across locales.")
        print(
            "- Keep MUST/SHALL/SHOULD counts close across locales (delta <= "
            f"{NORMATIVE_TOKEN_TOLERANCE})."
        )
        return 1

    print("i18n core-loop parity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

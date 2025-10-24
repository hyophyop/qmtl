"""
Audit docs for mixed-language content between Korean (ko) and English (en).

Writes a markdown report to docs/i18n_audit_report.md highlighting files that
likely contain the wrong-language paragraphs and showing sample lines.

Heuristics:
- For docs/en: flag if Hangul ratio > 2% overall, and list lines (>=30 chars)
  with Hangul ratio > 20%.
- For docs/ko: flag if Hangul ratio < 20% overall, and list lines (>=30 chars)
  with Hangul ratio < 20% but Latin ratio > 30%.

This is a quick signal to prioritize fixes; code blocks and inline code may
inflate Latin counts, so treat results as a starting point, not a verdict.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class FileFinding:
    path: str
    kind: str
    hang_ratio: float
    latin_ratio: float
    lines: List[Tuple[int, str]]


def char_stats(text: str) -> tuple[int, int, int]:
    hangul = sum(
        1
        for ch in text
        if ("\uAC00" <= ch <= "\uD7A3")
        or ("\u1100" <= ch <= "\u11FF")
        or ("\u3130" <= ch <= "\u318F")
    )
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    total = sum(1 for ch in text if not ch.isspace())
    return hangul, latin, total


def scan_locale(base_dir: str, locale: str) -> List[FileFinding]:
    root = os.path.join(base_dir, locale)
    findings: List[FileFinding] = []
    for dp, _dn, files in os.walk(root):
        for f in files:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            with open(p, "r", encoding="utf-8") as fh:
                txt = fh.read()
            h, l, t = char_stats(txt)
            rh = h / (t or 1)
            rl = l / (t or 1)

            lines: List[Tuple[int, str]] = []
            for i, line in enumerate(txt.splitlines(), 1):
                hh, ll, tt = char_stats(line)
                if tt < 30:
                    continue
                if locale == "en" and (hh / (tt or 1)) > 0.20:
                    lines.append((i, line.strip()))
                if (
                    locale == "ko"
                    and (hh / (tt or 1)) < 0.20
                    and (ll / (tt or 1)) > 0.30
                ):
                    lines.append((i, line.strip()))

            if locale == "en" and rh > 0.02:
                findings.append(
                    FileFinding(p, "en_has_hangul", rh, rl, lines[:20])
                )
            if locale == "ko" and rh < 0.20:
                findings.append(
                    FileFinding(p, "ko_low_hangul", rh, rl, lines[:20])
                )
    return findings


def write_report(base_dir: str, findings: List[FileFinding]) -> None:
    out = os.path.join(base_dir, "i18n_audit_report.md")
    findings = sorted(findings, key=lambda f: (f.kind, f.hang_ratio))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("# i18n Audit Report\n")
        fh.write("\n")
        fh.write(
            "This report lists markdown files that appear to mix languages or be mis-localized.\n"
        )
        fh.write(
            "Heuristics flag Korean pages with too little Hangul text, and English pages with Hangul present.\n\n"
        )
        for f in findings:
            fh.write(
                f"- {f.kind}: {f.hang_ratio:.1%} hangul, {f.latin_ratio:.1%} latin — `{f.path}`\n"
            )
        fh.write("\n---\n\n")
        for f in findings:
            fh.write(f"## {f.path}\n")
            fh.write(
                f"- Kind: {f.kind} — Hangul: {f.hang_ratio:.1%}, Latin: {f.latin_ratio:.1%}\n\n"
            )
            if f.lines:
                fh.write("Sample lines:\n")
                for n, line in f.lines:
                    # truncate long lines for readability
                    if len(line) > 180:
                        line = line[:180] + " …"
                    fh.write(f"- L{n}: {line}\n")
            fh.write("\n")
    print(f"Wrote report: {out}")


def main() -> None:
    base = os.path.join(os.path.dirname(__file__), "..", "docs")
    base = os.path.abspath(base)
    findings = []
    findings.extend(scan_locale(base, "en"))
    findings.extend(scan_locale(base, "ko"))
    write_report(base, findings)


if __name__ == "__main__":
    main()


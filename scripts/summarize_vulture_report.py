#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ENTRY_PATTERN = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+): unused (?P<kind>.+?) '(?P<name>.+?)' "
    r"\((?P<confidence>\d+)% confidence(?:, (?P<lines>\d+) line(?:s)?)?\)$"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a Vulture text report.")
    parser.add_argument("--input", required=True, help="Path to the raw Vulture text report.")
    parser.add_argument("--json-output", required=True, help="Where to write the summary JSON.")
    parser.add_argument(
        "--markdown-output",
        required=True,
        help="Where to write the Markdown summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    json_output = Path(args.json_output)
    markdown_output = Path(args.markdown_output)

    if not input_path.exists():
        payload = {"total_findings": 0, "kinds": {}, "top_paths": {}, "unparsed_lines": []}
        json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_output.write_text("# Vulture Report\n\nNo report was generated.\n", encoding="utf-8")
        return 0

    raw_lines = [line.strip() for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds: Counter[str] = Counter()
    top_paths: Counter[str] = Counter()
    unparsed_lines: list[str] = []

    for line in raw_lines:
        match = ENTRY_PATTERN.match(line)
        if not match:
            unparsed_lines.append(line)
            continue
        kinds[match.group("kind")] += 1
        top_paths[match.group("path")] += 1

    payload = {
        "total_findings": sum(kinds.values()),
        "kinds": dict(sorted(kinds.items())),
        "top_paths": dict(top_paths.most_common(10)),
        "unparsed_lines": unparsed_lines[:20],
    }
    json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Vulture Report",
        "",
        f"Total findings: {payload['total_findings']}",
        "",
        "## By kind",
    ]
    if payload["kinds"]:
        for kind, count in payload["kinds"].items():
            lines.append(f"- {kind}: {count}")
    else:
        lines.append("- No parsed findings.")

    lines.extend(["", "## Top paths"])
    if payload["top_paths"]:
        for path, count in payload["top_paths"].items():
            lines.append(f"- `{path}`: {count}")
    else:
        lines.append("- No parsed paths.")

    if payload["unparsed_lines"]:
        lines.extend(["", "## Unparsed lines", *[f"- `{line}`" for line in payload["unparsed_lines"]]])

    markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

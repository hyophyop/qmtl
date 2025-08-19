#!/usr/bin/env python
"""Validate TAGS metadata for node modules."""

from __future__ import annotations

import argparse
import ast
import json
import os
from collections import OrderedDict
from typing import Any, Dict, Tuple

REQUIRED_KEYS = ["scope", "family", "interval", "asset"]
RECOMMENDED_KEYS = ["window", "price", "side", "target_horizon", "label"]
VALID_SCOPES = {"indicator", "signal", "performance", "portfolio", "generator", "transform"}
INTERVAL_NORMALIZATION = {
    "60s": "1m",
    "60": "1m",
    "1m": "1m",
    "300s": "5m",
    "300": "5m",
    "5m": "5m",
    "3600s": "1h",
    "3600": "1h",
    "1h": "1h",
    "86400s": "1d",
    "86400": "1d",
    "1d": "1d",
}
CANONICAL_INTERVALS = {"1m", "5m", "1h", "1d"}


def normalize_interval(value: Any) -> Tuple[str, bool]:
    """Return normalized interval and validity."""
    if isinstance(value, (int, float)):
        value = str(int(value))
    if isinstance(value, str):
        value = value.lower()
        if value in INTERVAL_NORMALIZATION:
            norm = INTERVAL_NORMALIZATION[value]
            return norm, True
    return str(value), value in CANONICAL_INTERVALS


def load_tags(path: str) -> Tuple[Dict[str, Any], ast.Assign | None, ast.Module]:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    tags_node = None
    tags: Dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TAGS":
                    if isinstance(node.value, ast.Dict):
                        try:
                            tags = ast.literal_eval(node.value)
                        except Exception:
                            tags = {}
                    tags_node = node
    return tags, tags_node, tree


def write_tags(path: str, tree: ast.Module, node: ast.Assign | None, tags: Dict[str, Any]):
    # Build ordered dict
    ordered = OrderedDict()
    for key in REQUIRED_KEYS + RECOMMENDED_KEYS:
        if key in tags:
            ordered[key] = tags[key]
    # Include any additional keys
    for key, val in tags.items():
        if key not in ordered:
            ordered[key] = val
    dict_str = json.dumps(ordered, indent=4)
    lines = dict_str.splitlines()
    tag_lines = ["TAGS = " + lines[0]] + ["    " + l for l in lines[1:]]
    with open(path, "r", encoding="utf-8") as f:
        src_lines = f.read().splitlines()
    if node is None:
        insert_line = 0
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
            insert_line = tree.body[0].end_lineno
        new_lines = src_lines[:insert_line] + ["", *tag_lines, ""] + src_lines[insert_line:]
    else:
        new_lines = src_lines
        new_lines[node.lineno - 1 : node.end_lineno] = tag_lines
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")


def lint_file(path: str, fix: bool = False) -> Tuple[bool, str]:
    tags, node, tree = load_tags(path)
    errors = []
    if node is None:
        if fix:
            scaffold = {key: "TODO" for key in REQUIRED_KEYS + RECOMMENDED_KEYS}
            write_tags(path, tree, None, scaffold)
            return True, ""
        return False, "missing TAGS dict"

    fixed_tags: Dict[str, Any] = {}
    for key, val in tags.items():
        key_l = str(key).lower()
        if isinstance(val, list):
            errors.append(f"{key}: lists are not allowed")
            continue
        if isinstance(val, str):
            val_l = val.lower()
        else:
            val_l = val
        if key_l == "interval":
            norm, ok = normalize_interval(val_l)
            if not ok:
                errors.append(f"interval value '{val}' is invalid")
            elif norm != val_l:
                if fix:
                    val_l = norm
                else:
                    errors.append(f"interval '{val}' not normalized (expected {norm})")
        if key_l == "scope" and isinstance(val_l, str) and val_l not in VALID_SCOPES:
            errors.append(f"scope '{val_l}' is invalid")
        fixed_tags[key_l] = val_l
        if key != key_l or (isinstance(val, str) and val != val_l):
            if not fix:
                errors.append(f"{key}: keys and string values must be lowercase")
    for req in REQUIRED_KEYS:
        if req not in fixed_tags:
            if fix:
                fixed_tags[req] = "TODO"
            else:
                errors.append(f"missing required key: {req}")
    if fix and errors:
        errors = []
    if fix:
        write_tags(path, tree, node, fixed_tags)
    return not errors, "\n".join(errors)


def iter_py_files(path: str):
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                if name.endswith(".py") and name != "__init__.py":
                    yield os.path.join(root, name)
    else:
        if path.endswith(".py") and os.path.basename(path) != "__init__.py":
            yield path


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Lint TAGS dictionaries")
    parser.add_argument("files", nargs="+", help="Files or directories to lint")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues")
    args = parser.parse_args(argv)

    ok = True
    for target in args.files:
        for file in iter_py_files(target):
            valid, msg = lint_file(file, fix=args.fix)
            if not valid:
                ok = False
                print(f"{file}: {msg}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Validate TAGS metadata for node modules."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Tuple

from qmtl.utils.i18n import _

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


def validate_tags(tags: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Return normalized tags and a list of validation errors."""
    errors: List[str] = []
    fixed_tags: Dict[str, Any] = {}
    for key, val in tags.items():
        key_l = str(key).lower()
        if isinstance(val, list):
            errors.append(_("{key}: lists are not allowed").format(key=key))
            continue
        if isinstance(val, str):
            val_l = val.lower()
        else:
            val_l = val
        if key_l == "interval":
            norm, ok = normalize_interval(val_l)
            if not ok:
                errors.append(_("interval value '{value}' is invalid").format(value=val))
            elif norm != val_l:
                errors.append(
                    _("interval '{value}' not normalized (expected {expected})").format(
                        value=val, expected=norm
                    )
                )
                val_l = norm
        if key_l == "scope" and isinstance(val_l, str) and val_l not in VALID_SCOPES:
            errors.append(_("scope '{value}' is invalid").format(value=val_l))
        fixed_tags[key_l] = val_l
        if key != key_l or (isinstance(val, str) and val != val_l):
            errors.append(
                _("{key}: keys and string values must be lowercase").format(key=key)
            )
    for req in REQUIRED_KEYS:
        if req not in fixed_tags:
            errors.append(_("missing required key: {key}").format(key=req))
    return fixed_tags, errors


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


def apply_fixes(path: str, tags: Dict[str, Any], tree: ast.Module, node: ast.Assign | None) -> None:
    """Write normalized tags to disk, adding placeholders for missing keys."""
    fixed = dict(tags)
    keys = REQUIRED_KEYS + RECOMMENDED_KEYS if node is None else REQUIRED_KEYS
    for key in keys:
        fixed.setdefault(key, "TODO")
    write_tags(path, tree, node, fixed)


def lint_file(path: str, fix: bool = False) -> Tuple[bool, str]:
    tags, node, tree = load_tags(path)
    if node is None:
        if fix:
            apply_fixes(path, {}, tree, None)
            return True, ""
        return False, _("missing TAGS dict")

    fixed_tags, errors = validate_tags(tags)
    if fix:
        apply_fixes(path, fixed_tags, tree, node)
        return True, ""
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
    argparse._ = _
    parser = argparse.ArgumentParser(description=_("Lint TAGS dictionaries"))
    parser._ = _
    parser.add_argument("files", nargs="+", help=_("Files or directories to lint"))
    parser.add_argument("--fix", action="store_true", help=_("Attempt to fix issues"))
    args = parser.parse_args(argv)

    ok = True
    for target in args.files:
        for file in iter_py_files(target):
            valid, msg = lint_file(file, fix=args.fix)
            if not valid:
                ok = False
                if msg:
                    for line in msg.splitlines():
                        print(
                            _("{path}: {message}").format(path=file, message=line),
                            file=sys.stderr,
                        )
                else:
                    print(_("{path}: error").format(path=file), file=sys.stderr)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

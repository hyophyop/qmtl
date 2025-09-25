#!/usr/bin/env python3
"""Manage the strict-mode audit log table for schema governance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

DEFAULT_DOC = Path(__file__).resolve().parents[1] / "docs" / "operations" / "schema_registry_governance.md"


@dataclass
class AuditEntry:
    date: str
    schema_bundle_sha: str
    change_request: str
    validation_window: str
    notes: str


def format_row(values: Iterable[str]) -> str:
    return "| " + " | ".join(values) + " |"


def update_table(text: str, entry: AuditEntry) -> str:
    lines = text.splitlines()
    header_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("| Date") and "Schema Bundle SHA" in line:
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError("Strict mode audit table header not found")

    rows_start = header_idx + 2  # skip header and separator
    table_end = rows_start
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    new_row = format_row(
        [
            entry.date,
            entry.schema_bundle_sha,
            entry.change_request,
            entry.validation_window,
            entry.notes,
        ]
    )

    existing_rows = [line for line in lines[rows_start:table_end] if line.strip()]
    existing_rows = [row for row in existing_rows if "_TBD_" not in row]
    existing_rows = [row for row in existing_rows if entry.change_request not in row]
    existing_rows.insert(0, new_row)
    existing_rows.append(format_row(["_TBD_", "", "", "", ""]))

    lines[rows_start:table_end] = existing_rows
    return "\n".join(lines) + "\n"


def update_audit_log(doc: Path, entry: AuditEntry, *, dry_run: bool = False) -> str:
    text = doc.read_text(encoding="utf-8")
    updated = update_table(text, entry)
    if not dry_run:
        doc.write_text(updated, encoding="utf-8")
    return updated


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update the schema registry strict-mode audit log table.")
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC, help="Path to schema governance document")
    parser.add_argument("--date", dest="entry_date", default=None, help="ISO date for the promotion (default: today)")
    parser.add_argument("--schema-bundle-sha", required=True, help="SHA fingerprint of the schema bundle")
    parser.add_argument("--change-request", required=True, help="Link or reference for the change request")
    parser.add_argument("--validation-window", required=True, help="Duration of the canary validation window")
    parser.add_argument("--notes", default="", help="Additional rollout notes")
    parser.add_argument("--dry-run", action="store_true", help="Preview the updated table without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    entry = AuditEntry(
        date=args.entry_date or date.today().isoformat(),
        schema_bundle_sha=args.schema_bundle_sha,
        change_request=args.change_request,
        validation_window=args.validation_window,
        notes=args.notes,
    )
    updated = update_audit_log(args.doc, entry, dry_run=args.dry_run)
    if args.dry_run:
        print(updated, end="")
    else:
        print(f"Updated {args.doc} with audit entry for {entry.change_request}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

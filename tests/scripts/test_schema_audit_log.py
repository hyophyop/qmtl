from pathlib import Path

from scripts.schema.audit_log import AuditEntry, update_audit_log


SAMPLE_DOC = """---
title: example
---

# Header

| Date       | Schema Bundle SHA | Change Request | Validation Window | Notes |
|------------|------------------|----------------|-------------------|-------|
| _TBD_      |                  |                |                   |       |

"""


def _table_rows(text: str) -> list[str]:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("| Date"):
            rows: list[str] = []
            j = idx + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(lines[j])
                j += 1
            return rows
    raise AssertionError("table header missing")


def test_update_audit_log_inserts_entry(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(SAMPLE_DOC, encoding="utf-8")
    entry = AuditEntry(
        date="2025-10-01",
        schema_bundle_sha="abcd1234",
        change_request="CR-42",
        validation_window="48h",
        notes="all clear",
    )

    update_audit_log(doc, entry)
    updated = doc.read_text(encoding="utf-8")

    rows = _table_rows(updated)
    assert rows[0].startswith("| 2025-10-01 | abcd1234 | CR-42 | 48h | all clear |")
    assert sum(1 for row in rows if "_TBD_" in row) == 1


def test_dry_run_leaves_file_untouched(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(SAMPLE_DOC, encoding="utf-8")
    entry = AuditEntry(
        date="2025-10-02",
        schema_bundle_sha="deadbeef",
        change_request="CR-99",
        validation_window="72h",
        notes="",
    )

    preview = update_audit_log(doc, entry, dry_run=True)
    assert doc.read_text(encoding="utf-8") == SAMPLE_DOC
    assert "CR-99" in preview
    assert "_TBD_" in preview

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_sync() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check_doc_sync.py"],
        capture_output=True,
        text=True,
    )


def test_idea_files_are_ignored() -> None:
    idea_file = Path("docs/alphadocs/ideas/ignored_test.md")
    try:
        idea_file.write_text("test")
        proc = run_sync()
        assert proc.returncode == 0, proc.stdout + proc.stderr
    finally:
        idea_file.unlink(missing_ok=True)


def test_non_idea_files_trigger_error() -> None:
    doc_file = Path("docs/alphadocs/unregistered_test.md")
    try:
        doc_file.write_text("test")
        proc = run_sync()
        assert proc.returncode != 0
    finally:
        doc_file.unlink(missing_ok=True)

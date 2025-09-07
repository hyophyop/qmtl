"""Compatibility shim for tests importing check_doc_sync from qmtl.scripts.

This module delegates to the project-level script at `scripts/check_doc_sync.py`.
Keeping this thin wrapper under `qmtl/` avoids duplicating logic while
maintaining import paths expected by tests.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util
import types


def _load_root_script() -> types.ModuleType:
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "check_doc_sync.py"
    spec = importlib.util.spec_from_file_location("check_doc_sync_root", script_path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"Cannot locate root script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_root = _load_root_script()

# Re-export the callable API used by tests and CLI wiring
check_doc_sync = _root.check_doc_sync  # type: ignore[attr-defined]
main = _root.main  # type: ignore[attr-defined]

